"""Tests for the #359 evidence-selection harness: generic rules (C3), scoring
(§4-§6, P3) and the runner's sealing guards (§9.1). No services needed."""

import ast
import json
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

import evidence_selection_359 as runner  # noqa: E402
import evidence_selection_359_rules as rules  # noqa: E402
import evidence_selection_359_scoring as scoring  # noqa: E402

PRIMARY = ROOT / "DOCS" / "evaluations" / "359-primary"


def _load(name):
    return json.loads((PRIMARY / name).read_text(encoding="utf-8"))


def _graph(edges, extra=()):
    """edges: (from, to, rel, lines)."""
    g = rules.Graph()
    for frm, to, rel, lines in edges:
        g.out.setdefault(frm, []).append(rules.Edge(to, rel, tuple(lines)))
        g.nodes.update({frm, to})
    g.nodes.update(extra)
    g.nodes = {n for n in g.nodes if not n.startswith("EXTERNAL_")}
    return g


# ----------------------------------------------------------------- C3


def test_c3_rules_module_contains_no_ground_truth_terms():
    terms = scoring.forbidden_terms(
        _load("expected-chains.json"), _load("questions.json")
    )
    assert {
        "run_rag",
        "rag_orchestrator/src/core/service.py",
        "/v1/rag",
        "/api/embed",
    } <= terms
    result = scoring.c3_scan(runner.RULES_FILE.read_text(encoding="utf-8"), terms)
    assert result["clean"], result["hits"]


def test_c3_rules_module_imports_only_the_standard_library():
    tree = ast.parse(runner.RULES_FILE.read_text(encoding="utf-8"))
    imported = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imported |= {a.name.split(".")[0] for a in node.names}
        elif isinstance(node, ast.ImportFrom):
            imported.add((node.module or "").split(".")[0])
    assert imported <= {"__future__", "re", "dataclasses", "typing"}


def test_c3_regex_terms_keep_escaped_characters_literal():
    assert scoring._terms_from_regex(r'@router\.post\("/rag"') == {
        "router.post",
        "/rag",
    }
    assert scoring._terms_from_regex(r"\brun_rag\(") == {"run_rag"}
    assert scoring._terms_from_regex(r"self\._strict\(") == {"self._strict"}


def test_c3_scan_ignores_standard_method_calls_but_not_content():
    assert scoring.c3_scan("for k, v in d.items():\n    pass\n", {"items"})["clean"]
    for src in ("def items():\n    pass\n", 'X = "items"\n', "# items\n"):
        assert scoring.c3_scan(src, {"items"})["hits"] == ["items"], src


def test_c3_scan_flags_a_planted_term_and_reports_generic_overlap():
    src = 'X = "pkg/mod.py#do_thing"\n# route handler\n'
    res = scoring.c3_scan(src, {"pkg/mod.py#do_thing", "do_thing", "route"})
    assert res["hits"] == ["do_thing", "pkg/mod.py#do_thing"]
    assert res["allowed_generic_overlap"] == ["route"]
    assert not res["clean"]


# ----------------------------------------------------------------- Stage RI

H = "svc/src/api/routes.py#endpoint"


def test_ri_resolved_from_question_text_only():
    g = _graph(
        [("route:svc:POST:/v1/x", H, "HANDLED_BY", [])], ["route:svc:POST:/v1/x/y"]
    )
    ri = rules.identify_route("Trace the path from POST /v1/x.", g)
    assert ri["code"] == "resolved" and ri["handler"] == H
    assert ri["edges_used"] == [["route:svc:POST:/v1/x", H, "HANDLED_BY"]]


def test_ri_failure_codes():
    g = _graph(
        [
            ("route:a:GET:/items", H, "HANDLED_BY", []),
            ("route:b:GET:/items", H, "HANDLED_BY", []),
        ],
        ["route:c:POST:/orders"],
    )
    assert rules.identify_route("GET /items", g)["code"] == "ambiguous_route"
    unresolved = rules.identify_route("GET /api/items", g)
    assert unresolved["code"] == "unresolved_route"
    assert unresolved["handler"] is None and len(unresolved["suffix_candidates"]) == 2
    assert rules.identify_route("DELETE /nothing", g)["code"] == "no_route_node"
    assert rules.identify_route("POST /orders", g)["code"] == "handler_missing"
    assert rules.identify_route("How does it work?", g)["code"] == "no_route_node"


# ----------------------------------------------------------------- traversal

E, A, B, C, D = "m.py#e", "m.py#a", "m.py#b", "m.py#c", "m.py#d"


def test_g1_is_breadth_first_g2_depth_first_in_call_site_order():
    g = _graph(
        [
            (E, B, "CALL", [20]),
            (E, A, "CALL", [10]),
            (A, C, "CALL", [5]),
            (B, D, "CALL", [5]),
            (E, "EXTERNAL_SYMBOL:x.y", "CALL", [1]),
        ]
    )
    g1 = rules.traverse(g, E, "G1")
    g2 = rules.traverse(g, E, "G2")
    assert g1["functions"] == [E, A, B, C, D]
    assert g2["functions"] == [E, A, C, B, D]
    assert g2["suppressed_count"] == 1 and g2["suppressed"] == [
        [E, "EXTERNAL_SYMBOL:x.y"]
    ]


def test_depth_and_node_caps():
    chain = [f"m.py#f{i}" for i in range(10)]
    g = _graph([(chain[i], chain[i + 1], "CALL", [1]) for i in range(9)])
    assert len(rules.traverse(g, chain[0], "G2", max_depth=6)["functions"]) == 7
    capped = rules.traverse(g, chain[0], "G1", max_nodes=4)
    assert len(capped["functions"]) == 4 and capped["cap_hit"]


def test_ambiguous_call_site_is_recorded_and_not_followed():
    g = _graph(
        [
            (E, "x.py#K.run", "CALL", [7]),
            (E, "y.py#L.run", "CALL", [7]),
            (E, A, "CALL", [9]),
        ]
    )
    res = rules.traverse(g, E, "G2")
    assert res["functions"] == [E, A]
    assert res["ambiguous"] == [
        {"caller": E, "name": "run", "candidates": ["x.py#K.run", "y.py#L.run"]}
    ]


def test_string_literals_split_fstrings_into_segments():
    text = (
        'url = f"{settings.BASE}/v1/things/{tid}/sub"\nx = "/plain"\n"""doc /v1/no"""'
    )
    lits = rules.string_literals(text)
    assert "/v1/things/" in lits and "/sub" in lits and "/plain" in lits
    assert "/v1/no" not in lits


def test_g3_adds_unique_url_literal_route_handler_after_call_children():
    other = "svc2/api.py#serve"
    g = _graph(
        [
            (E, A, "CALL", [3]),
            ("route:svc2:POST:/v1/do", other, "HANDLED_BY", []),
            ("route:s3:GET:/dup", B, "HANDLED_BY", []),
            ("route:s4:GET:/dup", C, "HANDLED_BY", []),
        ]
    )
    texts = {E: 'u = f"{base}/v1/do"\nv = "/dup"\na()', A: "", other: ""}
    res = rules.traverse(g, E, "G3", text_of=lambda c: texts.get(c, ""))
    assert res["functions"] == [E, A, other]
    assert [E, "route:svc2:POST:/v1/do", "URL_LITERAL"] in res["edges_used"]
    assert any(a.get("literal") == "/dup" for a in res["ambiguous"])
    assert rules.traverse(g, E, "G2")["functions"] == [E, A]


def test_g0_keeps_trace_order_and_drops_placeholders():
    g = _graph([(E, A, "CALL", [1]), (E, B, "CALL", [2])])
    hops = [
        {"canonical_id": B, "parent_canonical_id": E, "relation_type": "CALL"},
        {
            "canonical_id": "EXTERNAL_SYMBOL:q",
            "parent_canonical_id": E,
            "relation_type": "CALL",
        },
        {"canonical_id": A, "parent_canonical_id": E, "relation_type": "CALL"},
    ]
    res = rules.from_trace(g, E, hops, truncated=False)
    assert res["functions"] == [E, B, A] and res["suppressed_count"] == 1


def test_passage_units():
    g = _graph([(E, A, "CALL", [2]), (E, B, "CALL", [3])])
    disc = rules.traverse(g, E, "G2")
    chunks = {
        E: [
            {"text": "def e():"},
            {"text": "    x = 1"},
            {"text": "    a()"},
            {"text": "    zb()"},
        ],
        A: [{"text": "def a(): pass"}],
        B: [{"text": "def b(): pass"}, {"text": "  more"}],
    }
    whole = rules.passages(g, disc, "P-whole", lambda c: chunks[c])
    call = rules.passages(g, disc, "P-call", lambda c: chunks[c])
    assert len(whole) == 7
    assert [c["text"] for c in call] == [
        "def e():",
        "    a()",
        "def a(): pass",
        "def b(): pass",
    ]


# ----------------------------------------------------------------- scoring


def _rel(**kw):
    base = {
        "id": "R",
        "tier": "core",
        "caller": A,
        "callee": B,
        "witness_regex": r"\bb\(",
        "lines": [1],
        "resolution_class": "static_direct",
    }
    return {**base, **kw}


def _chunk(label, text):
    return {"label": label, "text": text}


def test_support_categories():
    rel = _rel()
    hit = [_chunk(A, "b()")]
    edge = [[A, B, "CALL"]]
    assert (
        scoring.categorize(rel, hit, edge, set(), True)["category"]
        == "graph_and_source"
    )
    assert scoring.categorize(rel, hit, [], set(), True)["category"] == "source_only"
    assert (
        scoring.categorize(rel, [_chunk(B, "b()")], edge, set(), True)["category"]
        == "unresolved"
    )
    assert (
        scoring.categorize(rel, [], edge, set(), False)["category"]
        == "source_valid_index_missing"
    )


def test_dispatch_without_configuring_evidence_is_an_error():
    rel = _rel(
        resolution_class="dynamic_dispatch",
        callee=None,
        dispatch_candidates=[B, C],
        configured_by="R6",
    )
    hit = [_chunk(A, "b()")]
    err = scoring.categorize(rel, hit, [[A, B, "CALL"]], set(), True)
    assert err["category"] == "unwarranted_disambiguation"
    ok = scoring.categorize(rel, hit, [[A, B, "CALL"]], {"R6"}, True)
    assert ok["category"] == "graph_and_source"
    assert scoring.categorize(rel, hit, [], set(), True)["category"] == "source_only"


def test_route_relationship_structural_alternative():
    rel = _rel(resolution_class="route", callee=None, route_node="route:s:GET:/x")
    used = [["route:s:GET:/x", A, "HANDLED_BY"]]
    res = scoring.categorize(rel, [], used, set(), True)
    assert (
        res["category"] == "graph_and_source"
        and res["basis"] == "structural_handled_by"
    )
    assert scoring.categorize(rel, [], [], set(), True)["category"] == "unresolved"


def test_sufficiency_requires_every_core_relationship_and_reasons():
    r1 = _rel(id="R1")
    r2 = _rel(id="R2", caller=C, witness_regex=r"zz")
    r3 = _rel(id="R3", tier="supporting", caller=D)
    req = [_chunk(A, "b()"), _chunk(C, "zz")]
    res = scoring.score_delivery([r1, r2, r3], [req[0]], req, [A, C], [], {})
    assert res["sufficiency"] == "FAIL" and res["core_supported"] == 1
    assert res["relationships"]["R2"]["reason"] == "cut_by_budget"
    assert res["relationships"]["R3"]["reason"] == "not_discovered"
    res2 = scoring.score_delivery([r1, r2], [], [], [A, C], [], {})
    assert res2["relationships"]["R1"]["reason"] == "not_selected"
    full = scoring.score_delivery([r1, r2, r3], req, req, [A, C], [], {})
    assert full["sufficiency"] == "PASS" and full["supporting_supported"] == 0


def test_selection_fan_out_counts_non_chain_functions_before_last_chain_function():
    m = scoring.selection_metrics([_rel()], [E, A, C, D, B, "z.py#q"])
    assert m["chain_positions"] == {A: 2, B: 5}
    assert m["fan_out_before_last_chain_function"] == 3


def test_minimum_evidence_bound_picks_cheapest_cover():
    r1 = _rel(id="R1", witness_regex="x1")
    r2 = _rel(id="R2", witness_regex="x2")
    chunks = {A: [_chunk(A, "x1 x2"), _chunk(A, "x1"), _chunk(A, "x2")]}
    b = scoring.minimum_evidence_bound([r1, r2], chunks, False)
    expected = scoring.render_cost(A, "x1 x2", True)
    assert b["bytes"] == expected and b["feasible_at"]["4096"]
    missing = scoring.minimum_evidence_bound(
        [_rel(id="R9", witness_regex="nope")], chunks, False
    )
    assert missing["bytes"] is None and missing["uncoverable"] == ["R9"]


def test_source_witness_check_at_recorded_lines():
    rel = _rel(witness_regex=r"b\(", lines=[2])
    assert scoring.source_has_witness(rel, "x\nb()\n")["valid"]
    assert not scoring.source_has_witness(rel, "b()\nx\n")["valid"]


def test_load_verified_refuses_hash_mismatch(tmp_path):
    f = tmp_path / "sealed.json"
    f.write_text('{"a": 1}\n', encoding="utf-8")
    assert scoring.load_verified(f, scoring.sha256_file(f)) == {"a": 1}
    with pytest.raises(SystemExit):
        scoring.load_verified(f, "0" * 64)


# ----------------------------------------------------------------- runner guards


def test_runner_refuses_sealed_files_before_the_e2e_freeze(tmp_path):
    runner.refuse_sealed_present("C7", tmp_path)
    (tmp_path / "expected-chains.json").write_text("{}", encoding="utf-8")
    with pytest.raises(SystemExit):
        runner.refuse_sealed_present("C7", tmp_path)
    runner.refuse_sealed_present("primary", tmp_path)


def test_self_repo_sets_are_pinned_to_the_frozen_generation():
    runner.check_inputs("C7", runner.SELF_REPO_ID, runner.SELF_GENERATION)
    with pytest.raises(SystemExit):
        runner.check_inputs("C7", runner.SELF_REPO_ID, "other-generation")
    runner.check_inputs("H", "mealie-repo", "mealie-generation")


def test_es_fingerprint_ignores_nothing_that_matters():
    es = {
        "G2": {
            "discovery": {"functions": [E]},
            "units": {"P-call": {"delivered": {"4096": {"chunk_ids": ["c"]}}}},
        }
    }
    other = json.loads(json.dumps(es))
    assert runner.es_fingerprint(es) == runner.es_fingerprint(other)
    other["G2"]["units"]["P-call"]["delivered"]["4096"]["chunk_ids"] = ["d"]
    assert runner.es_fingerprint(es) != runner.es_fingerprint(other)


# ----------------------------------------------------------------- primary files


def test_primary_files_transcribe_section_4():
    chains = _load("expected-chains.json")["chains"]["P0"]
    assert len(chains) == 18 and sum(r["tier"] == "core" for r in chains) == 12
    assert set(_load("oracle-entry-points.json")) == {"set", "entry_points"}
    q = _load("questions.json")
    assert q["protocol"]["sha256"] == runner.PROTOCOL_SHA256
    assert q["questions"][0]["question"].startswith(
        "Trace the execution path from POST /v1/rag"
    )


def _has_commit(sha):
    return (
        subprocess.run(
            ["git", "-C", str(ROOT), "cat-file", "-e", f"{sha}^{{commit}}"],
            capture_output=True,
        ).returncode
        == 0
    )


@pytest.mark.skipif(
    not _has_commit("9f039c4"), reason="pinned commit not in this clone"
)
def test_primary_witnesses_hold_at_the_pinned_commit():
    for rel in _load("expected-chains.json")["chains"]["P0"]:
        path = rel["caller"].split("#", 1)[0]
        text = subprocess.run(
            ["git", "-C", str(ROOT), "show", f"9f039c4:{path}"],
            capture_output=True,
            text=True,
            encoding="utf-8",
            check=True,
        ).stdout
        assert scoring.source_has_witness(rel, text)["valid"], rel["id"]


@pytest.mark.skipif(
    not _has_commit(runner.PROTOCOL_COMMIT), reason="protocol commit not in clone"
)
def test_protocol_on_head_is_the_frozen_version():
    assert runner.protocol_identity()["sha256"] == runner.PROTOCOL_SHA256


# ----------------------------------------------------------------- pipeline

SVC_ROUTE, OTHER_ROUTE = "route:svc:GET:/v1/items", "route:svc2:POST:/v1/other"
ENTRY, WORK, STORE, SERVE = "h.py#entry", "a.py#work", "b.py#store", "c.py#serve"
TEXTS = {
    ENTRY: ['@router.get("/v1/items")\ndef entry():', "    return work()"],
    WORK: ["def work():", '    url = f"{base}/v1/other"\n    store()'],
    STORE: ["def store(): pass"],
    SERVE: ["def serve(): pass"],
}


class FakeServices:
    """Stands in for the read-only HTTP stack."""

    def __init__(self, host, repo_id, generation, qvec):
        self.repo_id, self.generation = repo_id, generation
        self.node_doc, self.full_pages = {}, []

    def generation_state(self):
        return {"ingestion_id": self.generation, "generation_status": "ready"}

    def require_ready(self):
        return self.generation_state()

    def versions(self):
        return {"8004": {"git_sha": "test"}}

    def graph_export(self):
        nodes = [*TEXTS, SVC_ROUTE, OTHER_ROUTE]
        self.node_doc = {c: f"doc-{c}" for c in TEXTS}
        rel = {
            SVC_ROUTE: [(ENTRY, "HANDLED_BY", [])],
            OTHER_ROUTE: [(SERVE, "HANDLED_BY", [])],
            ENTRY: [(WORK, "CALL", [2])],
            WORK: [(STORE, "CALL", [3]), ("EXTERNAL_SYMBOL:log.info", "CALL", [1])],
        }
        return {
            "ingestion_id": self.generation,
            "nodes": [{"canonical_id": c, "document_id": f"doc-{c}"} for c in nodes],
            "relationships": {
                f: [
                    {
                        "to_canonical_id": t,
                        "relation_type": r,
                        "relationship_metadata": {"call_sites": ln},
                    }
                    for t, r, ln in es
                ]
                for f, es in rel.items()
            },
        }

    def lookup(self, cids):
        self.node_doc.update({c: f"doc-{c}" for c in cids if c in TEXTS})

    def chunks(self, cid, label_of):
        out = []
        for i, t in enumerate(TEXTS.get(cid, [])):
            row = {
                "chunk_id": f"{cid}:{i}",
                "document_id": f"doc-{cid}",
                "text": t,
                "metadata": {
                    "chunk_index": i,
                    "source_metadata": {"canonical_id": cid},
                },
            }
            out.append(
                {
                    "chunk_id": row["chunk_id"],
                    "document_id": row["document_id"],
                    "chunk_index": i,
                    "label": str(label_of(row)),
                    "text": t,
                    "row": row,
                }
            )
        return out

    def trace(self, start):
        hop = {"parent_canonical_id": ENTRY, "relation_type": "CALL"}
        return {
            "hops": [
                {**hop, "canonical_id": WORK},
                {**hop, "canonical_id": STORE, "parent_canonical_id": WORK},
            ],
            "truncated": False,
        }


def _write(path, obj):
    path.write_text(json.dumps(obj) + "\n", encoding="utf-8", newline="\n")
    return scoring.sha256_file(path)


def _rels():
    def rel(rid, caller, callee, rx, cls, **kw):
        return {
            "id": rid,
            "tier": "core",
            "caller": caller,
            "callee": callee,
            "witness_regex": rx,
            "lines": [1],
            "resolution_class": cls,
            **kw,
        }

    return [
        rel(
            "R1",
            ENTRY,
            None,
            r'@router\.get\("/v1/items"\)',
            "route",
            route_node=SVC_ROUTE,
        ),
        rel("R2", ENTRY, WORK, r"\bwork\(", "static_direct"),
        rel("R3", WORK, STORE, r"\bstore\(", "static_direct"),
        rel("R4", WORK, OTHER_ROUTE, "/v1/other", "cross_service_http"),
    ]


@pytest.mark.skipif(
    not _has_commit(runner.PROTOCOL_COMMIT), reason="protocol commit not in clone"
)
def test_sealed_pipeline_end_to_end_on_a_fake_stack(tmp_path, monkeypatch):
    monkeypatch.setattr(runner, "Services", FakeServices)
    set_dir, sealed, raw = tmp_path / "set", tmp_path / "sealed", tmp_path / "raw"
    for d in (set_dir, sealed, raw):
        d.mkdir()
    question = {
        "qid": "C7-1",
        "route": "GET /v1/items",
        "question": "Trace the execution path from GET /v1/items.",
    }
    proto = {"commit": runner.PROTOCOL_COMMIT, "sha256": runner.PROTOCOL_SHA256}
    qsha = _write(
        set_dir / "questions.json",
        {"set": "C7", "protocol": proto, "source_commit": "x", "questions": [question]},
    )
    oracle = sealed / "oracle.json"
    osha = _write(oracle, {"set": "C7", "entry_points": {"C7-1": ENTRY}})
    chains = sealed / "chains.json"
    csha = _write(chains, {"set": "C7", "chains": {"C7-1": _rels()}})
    qv = tmp_path / "qv.json"
    qv.write_text('{"query_vector": [0.0]}', encoding="utf-8")
    base = [
        "--set", str(set_dir), "--questions-sha256", qsha, "--host", "http://x",
        "--repo-id", runner.SELF_REPO_ID, "--generation", runner.SELF_GENERATION,
        "--query-vector-file", str(qv),
    ]  # fmt: skip
    pre, e2e, orc = raw / "pre.json", raw / "e2e.json", raw / "orc.json"

    assert runner.main(["preflight", *base, "--out", str(pre)]) == 0
    run_e2e = ["run-e2e", *base, "--preflight", str(pre), "--out", str(e2e)]
    (set_dir / "expected-chains.json").write_text("{}", encoding="utf-8")
    with pytest.raises(SystemExit):  # a sealed file present before the freeze
        runner.main(run_e2e)
    (set_dir / "expected-chains.json").unlink()
    assert runner.main(run_e2e) == 0
    esha = scoring.sha256_file(e2e)
    run_orc = ["run-oracle", *base, "--e2e", str(e2e), "--e2e-sha256", esha,
               "--oracle", str(oracle)]  # fmt: skip
    with pytest.raises(SystemExit):  # wrong oracle hash
        runner.main([*run_orc, "--oracle-sha256", "0" * 64, "--out", str(raw / "x")])
    assert runner.main([*run_orc, "--oracle-sha256", osha, "--out", str(orc)]) == 0
    score = [
        "score", *base, "--chains", str(chains), "--chains-sha256", csha,
        "--e2e", str(e2e), "--e2e-sha256", esha, "--oracle-record", str(orc),
        "--oracle-record-sha256", scoring.sha256_file(orc),
        "--out", str(raw / "score.json"),
    ]  # fmt: skip
    assert runner.main(score) == 0

    q = json.loads(e2e.read_text(encoding="utf-8"))["results"]["C7-1"]
    assert q["ri"]["code"] == "resolved" and q["a0"]["status"].startswith("not run")
    assert q["es"]["G3"]["discovery"]["functions"] == [ENTRY, WORK, STORE, SERVE]
    assert q["es"]["G2"]["discovery"]["functions"] == [ENTRY, WORK, STORE]
    o = json.loads(orc.read_text(encoding="utf-8"))
    assert o["label"].startswith("ORACLE-ENTRY")
    assert o["results"]["C7-1"]["consistency"] == {
        "ri_handler_equals_oracle": True,
        "es_identical": True,
    }
    s = json.loads((raw / "score.json").read_text(encoding="utf-8"))["results"]
    s = s["C7-1"]
    g3 = s["E2E"]["G3"]["units"]["P-whole"]["4096"]
    g2 = s["E2E"]["G2"]["units"]["P-whole"]["4096"]
    assert g3["sufficiency"] == "PASS"
    assert g3["relationships"]["R4"]["category"] == "graph_and_source"
    assert g2["relationships"]["R4"]["category"] == "source_only"
    assert g3["relationships"]["R1"]["basis"] == "structural_handled_by"
    assert s["end_to_end_success"]["G3/P-whole/4096"] is True
    assert s["ORACLE-ENTRY"]["label"].startswith("ORACLE-ENTRY")
    assert s["ri"]["ri_error_wrong_handler"] is False
    assert s["minimum_evidence_bound"][0]["label"].startswith("ORACLE BOUND")
