"""Issue #359: read-only runner for the route-grounded evidence-selection
diagnostic (frozen protocol, DOCS/evaluations/2026-11-13-359-...-protocol.md).

Each stage is a separate command and writes its own raw record (never
overwritten) whose sha256 is printed for posting on #359 (§7, §9.1):

  preflight   §7.1: generation ready, service SHAs, protocol and rules hashes,
              C3 scan; for the public primary set also every §4 witness in
              the caller's stored text (aborts if one is missing).
  run-e2e     §7.2: Stage RI + Stage ES under E2E (and A0 for the primary
              set only, owner decision P4). Reads the questions file only;
              refuses to run while a sealed file sits in a non-primary set
              directory.
  run-oracle  §7.3: verifies the revealed oracle entry-points file and the
              frozen E2E record by hash, then runs ES under ORACLE-ENTRY.
  score       §7.4: verifies the expected-chains file by hash and scores the
              two frozen records; P3 recheck against stored text and pinned
              source; C3 rescan with the revealed terms.

Read-only HTTP only: generation, graph export, /trace, node lookup,
search-by-doc, /version. No generation, embedding, ingestion, SQL or writes.
The selection rules live in evidence_selection_359_rules.py; scoring in
evidence_selection_359_scoring.py (C3, C4).

    python scripts/evidence_selection_359.py preflight
        --set DOCS/evaluations/359-primary --host http://HOST
        --repo-id ID --generation GEN --out RAW/x.json
        --query-vector-file RAW/2026-11-12-345-retrieval-candidates-run3.json
"""

from __future__ import annotations

import argparse
import asyncio
import hashlib
import importlib
import json
import logging
import os
import subprocess
import sys
import threading
from datetime import datetime, timezone
from http.server import HTTPServer
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
import evidence_selection_359_rules as rules  # noqa: E402
import evidence_selection_359_scoring as scoring  # noqa: E402

SCHEMA = "evidence_selection_359.v1"
PROTOCOL_PATH = (
    "DOCS/evaluations/2026-11-13-359-route-grounded-evidence-selection-protocol.md"
)
PROTOCOL_COMMIT = "45f34e1"
PROTOCOL_SHA256 = "ca1d1ed5f192910c78ad7a179fb75f3131a6f796f2b3d27244698212c5049535"
# §3 fixed inputs for the self-repository sets (primary and C7).
SELF_REPO_ID = "f7641840-ba13-5f9d-9ae6-87e1f924709d"
SELF_GENERATION = "8cbedbb9-9ad6-4c63-83f7-2b7d7659f7e5"
SELF_SETS = ("primary", "C7")
SEALED_FILES = ("oracle-entry-points.json", "expected-chains.json")
TRACE_RELS = "HANDLED_BY,CALL"
SEARCH_BY_DOC_K = 100  # §3 and the vector store's cap
BUDGETS = scoring.BUDGETS
RULES_FILE = ROOT / "scripts" / "evidence_selection_359_rules.py"


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def protocol_identity() -> dict:
    """C2: the protocol on HEAD must be the frozen one, byte for byte."""
    frozen = subprocess.run(
        ["git", "-C", str(ROOT), "show", f"{PROTOCOL_COMMIT}:{PROTOCOL_PATH}"],
        capture_output=True,
        check=True,
    ).stdout
    head = subprocess.run(
        ["git", "-C", str(ROOT), "show", f"HEAD:{PROTOCOL_PATH}"],
        capture_output=True,
        check=True,
    ).stdout
    if sha256_bytes(frozen) != PROTOCOL_SHA256 or sha256_bytes(head) != PROTOCOL_SHA256:
        raise SystemExit("protocol file differs from the frozen version (C2)")
    return {"path": PROTOCOL_PATH, "commit": PROTOCOL_COMMIT, "sha256": PROTOCOL_SHA256}


def code_identity() -> dict:
    files = {
        "rules": RULES_FILE,
        "scoring": ROOT / "scripts" / "evidence_selection_359_scoring.py",
        "runner": Path(__file__).resolve(),
    }
    return {
        "git_head": subprocess.run(
            ["git", "-C", str(ROOT), "rev-parse", "HEAD"],
            capture_output=True,
            text=True,
        ).stdout.strip(),
        "rules_version": rules.RULES_VERSION,
        "scoring_version": scoring.SCORING_VERSION,
        "sha256": {k: sha256_bytes(p.read_bytes()) for k, p in files.items()},
    }


def write_record(path: Path, data: dict) -> str:
    blob = (json.dumps(data, ensure_ascii=False, indent=1, default=str) + "\n").encode()
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(fd, "wb") as fh:
        fh.write(blob)
    digest = sha256_bytes(blob)
    print(json.dumps({"record": path.name, "sha256": digest}))
    return digest


def load_set(set_dir: Path, questions_sha256: str | None) -> tuple[str, dict, str]:
    qpath = set_dir / "questions.json"
    digest = scoring.sha256_file(qpath)
    if questions_sha256 and digest != questions_sha256.lower():
        raise SystemExit(f"questions.json sha256 {digest} != posted {questions_sha256}")
    questions = json.loads(qpath.read_text(encoding="utf-8"))
    name = questions["set"]
    if name != "primary" and not questions_sha256:
        raise SystemExit("--questions-sha256 (as posted on #359) is required")
    if questions.get("protocol", {}).get("sha256") != PROTOCOL_SHA256:
        raise SystemExit("questions.json names a different protocol version")
    return name, questions, digest


def check_inputs(set_name: str, repo_id: str, generation: str) -> None:
    if set_name in SELF_SETS and (repo_id, generation) != (
        SELF_REPO_ID,
        SELF_GENERATION,
    ):
        raise SystemExit("self-repository sets are fixed to §3's repo and generation")


def refuse_sealed_present(set_name: str, set_dir: Path) -> None:
    if set_name == "primary":
        return  # §4 is public; the runner still never opens these in run-e2e
    present = [f for f in SEALED_FILES if (set_dir / f).exists()]
    if present:
        raise SystemExit(f"sealed files present before the E2E freeze: {present}")


# ----------------------------------------------------------------- services


class Services:
    """Read-only HTTP access to the deployed stack."""

    def __init__(self, host: str, repo_id: str, generation: str, query_vector: list):
        import httpx

        self.host, self.repo_id, self.generation = host, repo_id, generation
        self.qvec = query_vector
        self.client = httpx.Client(timeout=180)
        self.node_doc: dict[str, str] = {}
        self._chunks: dict[str, list[dict]] = {}
        self.full_pages: list[str] = []

    def url(self, port: int, path: str) -> str:
        return f"{self.host}:{port}{path}"

    def generation_state(self) -> dict:
        r = self.client.get(self.url(8001, f"/v1/repos/{self.repo_id}/generation"))
        r.raise_for_status()
        return r.json()

    def require_ready(self) -> dict:
        state = self.generation_state()
        if (
            state.get("ingestion_id") != self.generation
            or state.get("generation_status") != "ready"
        ):
            raise SystemExit(f"generation changed or not ready: {state}")
        return state

    def versions(self) -> dict:
        out = {}
        for port in (8001, 8002, 8003, 8004):
            try:
                out[str(port)] = self.client.get(self.url(port, "/version")).json()
            except Exception as exc:  # recorded, not fatal
                out[str(port)] = {"error": f"{type(exc).__name__}"}
        return out

    def graph_export(self) -> dict:
        r = self.client.get(
            self.url(8001, f"/v1/graph/repos/{self.repo_id}"),
            params={"expected_generation_id": self.generation},
        )
        r.raise_for_status()
        data = r.json()
        if data.get("ingestion_id") != self.generation:
            raise SystemExit("graph export is not the pinned generation")
        self.node_doc = {n["canonical_id"]: n["document_id"] for n in data["nodes"]}
        return data

    def lookup(self, cids: list[str]) -> None:
        missing = [c for c in cids if c not in self.node_doc]
        if not missing:
            return
        r = self.client.post(
            self.url(8001, f"/v1/graph/repos/{self.repo_id}/nodes/lookup"),
            json={"canonical_ids": missing},
        )
        r.raise_for_status()
        for n in r.json().get("nodes", []):
            self.node_doc[n["canonical_id"]] = n["document_id"]

    def chunks(self, cid: str, label_of) -> list[dict]:
        if cid in self._chunks:
            return self._chunks[cid]
        doc = self.node_doc.get(cid)
        rows: list[dict] = []
        if doc:
            r = self.client.post(
                self.url(8002, "/v1/vectors/search-by-doc"),
                json={
                    "document_id": doc,
                    "k": SEARCH_BY_DOC_K,
                    "query_vector": self.qvec,
                    "ingestion_id": self.generation,
                    "repo_id": self.repo_id,
                },
            )
            r.raise_for_status()  # a 422 must not read as "no text"
            rows = r.json().get("results", [])
            rows.sort(key=lambda x: (x.get("metadata") or {}).get("chunk_index", 0))
            if len(rows) >= SEARCH_BY_DOC_K:
                self.full_pages.append(cid)  # P5: ranking vector could matter
        out = []
        for i, row in enumerate(rows):
            out.append(
                {
                    "chunk_id": str(row.get("chunk_id") or f"{doc}:{i}"),
                    "document_id": row.get("document_id"),
                    "chunk_index": (row.get("metadata") or {}).get("chunk_index"),
                    "label": str(label_of(row) or ""),
                    "text": str(row.get("text", "")),
                    "row": row,
                }
            )
        self._chunks[cid] = out
        return out

    def trace(self, start: str) -> dict:
        r = self.client.get(
            self.url(8004, f"/v1/repos/{self.repo_id}/trace"),
            params={
                "start": start,
                "relation_types": TRACE_RELS,
                "direction": "forward",
            },
        )
        r.raise_for_status()
        return r.json()


def import_adapter():
    sys.path.insert(0, str(ROOT / "rag_orchestrator"))
    cwd = os.getcwd()
    os.chdir(ROOT / "rag_orchestrator")
    try:
        return importlib.import_module("src.retrieval.agent_adapter")
    finally:
        os.chdir(cwd)


# ----------------------------------------------------------------- stage ES


def run_es(
    svc: Services, graph: rules.Graph, entry: str, adapter, chunk_table: dict
) -> dict:
    """Arms G0-G3 x units x budgets from one entry handler (§5, §5b)."""

    def chunks_of(cid: str) -> list[dict]:
        out = svc.chunks(cid, adapter._source_label)
        for c in out:
            chunk_table.setdefault(
                c["chunk_id"],
                {k: c[k] for k in ("label", "document_id", "chunk_index", "text")},
            )
        return out

    def text_of(cid: str) -> str:
        return "\n".join(c["text"] for c in chunks_of(cid))

    arms: dict[str, Any] = {}
    for arm in rules.ARMS:
        if arm == "G0":
            body = svc.trace(entry)
            disc = rules.from_trace(
                graph, entry, body.get("hops", []), body.get("truncated")
            )
            disc["trace_meta"] = {
                k: body.get(k) for k in ("ingestion_id", "truncated", "depth_limited")
            }
        else:
            disc = rules.traverse(graph, entry, arm, text_of=text_of)
        units = {}
        for unit in rules.UNITS:
            requested = rules.passages(graph, disc, unit, chunks_of)
            rows = [c["row"] for c in requested]
            by_row = {id(c["row"]): c["chunk_id"] for c in requested}
            delivered = {}
            for b in BUDGETS:
                got = adapter.assemble_context(rows, b)
                delivered[str(b)] = {
                    "chunk_ids": [by_row[id(r)] for r in got.chunks],
                    "bytes": got.token_count,
                    "context_sha256": sha256_bytes(got.text.encode("utf-8")),
                }
            units[unit] = {
                "requested_chunk_ids": [c["chunk_id"] for c in requested],
                "requested_bytes": adapter.assemble_context(rows, 2**63).token_count,
                "delivered": delivered,
            }
        arms[arm] = {"discovery": disc, "units": units}
    return arms


def es_fingerprint(es: dict | None) -> str | None:
    if es is None:
        return None
    slim = {
        a: {
            "functions": v["discovery"]["functions"],
            "delivered": {u: x["delivered"] for u, x in v["units"].items()},
        }
        for a, v in es.items()
    }
    return sha256_bytes(json.dumps(slim, sort_keys=True).encode())


# ----------------------------------------------------------------- A0


def run_a0(args, question: str, query_vector: list) -> dict:
    """A0 (§5): the unchanged local /v1/rag path with the stored Step 0 query
    vector (no embedding call) and generation stubbed (no model call)."""

    import retrieval_candidates_345 as rc

    server = HTTPServer(("127.0.0.1", 0), rc._LLMStub)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    sys.path.insert(0, str(ROOT))
    sys.path.insert(0, str(ROOT / "rag_orchestrator"))
    config: Any = importlib.import_module("src.core.config")
    from rag_orchestrator.src.core import config as package_config

    settings = config.Settings(
        _env_file=None,
        OLLAMA_BASE_URL="http://127.0.0.1:9",  # never contacted: embed is stubbed
        INGESTION_SERVICE_URL=f"{args.host}:8001",
        VECTOR_STORE_URL=f"{args.host}:8002",
        LLM_SERVICE_URL=f"http://127.0.0.1:{server.server_port}",
    )
    config.get_settings = lambda: settings
    package_config.get_settings = lambda: settings
    service: Any = importlib.import_module("src.core.service")
    adapter = importlib.import_module("src.retrieval.agent_adapter")
    observed: dict = {}
    original_assemble, original_embed = service.assemble_context, service.embed_query

    def observe_assemble(chunks, budget):
        result = original_assemble(chunks, budget)
        if budget > 10**9:
            observed["pool"] = list(chunks)
        else:
            observed["final_budget"] = budget
        return result

    def stored_vector(*_a, **_k):
        observed["embed_calls"] = observed.get("embed_calls", 0) + 1
        return query_vector

    service.assemble_context = observe_assemble
    service.embed_query = stored_vector
    logging.disable(logging.CRITICAL)
    try:
        asyncio.run(service.run_rag(query=question, repo_id=args.repo_id))
    finally:
        service.assemble_context, service.embed_query = (
            original_assemble,
            original_embed,
        )
        server.shutdown()
        server.server_close()
        logging.disable(logging.NOTSET)
    pool = observed.get("pool", [])
    table, ids = {}, []
    for i, row in enumerate(pool):
        cid = str(row.get("chunk_id") or f"a0:{i}")
        ids.append(cid)
        table[cid] = {
            "label": str(adapter._source_label(row) or ""),
            "document_id": row.get("document_id"),
            "chunk_index": (row.get("metadata") or {}).get("chunk_index"),
            "text": str(row.get("text", "")),
        }
    by_row = {id(r): ids[i] for i, r in enumerate(pool)}
    delivered = {}
    for b in BUDGETS:
        got = adapter.assemble_context(pool, b)
        delivered[str(b)] = {
            "chunk_ids": [by_row[id(r)] for r in got.chunks],
            "bytes": got.token_count,
            "context_sha256": sha256_bytes(got.text.encode("utf-8")),
        }
    return {
        "condition": "E2E reference (A0 takes the question directly)",
        "observed_final_budget": observed.get("final_budget"),
        "stubbed_embed_calls": observed.get("embed_calls", 0),
        "pool_chunk_ids": ids,
        "functions": list(dict.fromkeys(t["label"] for t in table.values())),
        "delivered": delivered,
        "chunks": table,
    }


# ----------------------------------------------------------------- commands


def _services(args) -> tuple[Services, list]:
    qvec = json.loads(Path(args.query_vector_file).read_text(encoding="utf-8"))[
        "query_vector"
    ]
    return Services(args.host, args.repo_id, args.generation, qvec), qvec


def _envelope(args, stage: str, set_name: str, qsha: str) -> dict:
    return {
        "schema": SCHEMA,
        "stage": stage,
        "captured_at": datetime.now(timezone.utc).isoformat(),
        "evidence_class": "development evidence (ADR-054); not a generalization result"
        if set_name in SELF_SETS
        else "held-out (ADR-054 §5)",
        "protocol": protocol_identity(),
        "code": code_identity(),
        "interpretations": rules.INTERPRETATIONS,
        "set": set_name,
        "questions_sha256": qsha,
        "repo_id": args.repo_id,
        "generation": args.generation,
    }


def cmd_preflight(args) -> int:
    set_dir = Path(args.set)
    set_name, questions, qsha = load_set(set_dir, args.questions_sha256)
    check_inputs(set_name, args.repo_id, args.generation)
    svc, _ = _services(args)
    adapter = import_adapter()
    before = svc.require_ready()
    record = _envelope(args, "preflight", set_name, qsha)
    record["service_versions"] = svc.versions()
    record["c3_scan"] = scoring.c3_scan(
        RULES_FILE.read_text(encoding="utf-8"),
        scoring.forbidden_terms(
            json.loads(
                (ROOT / "DOCS/evaluations/359-primary/expected-chains.json").read_text(
                    encoding="utf-8"
                )
            ),
            questions if set_name == "primary" else None,
        ),
    )
    witnesses = None
    if set_name == "primary":
        chains = json.loads(
            (set_dir / "expected-chains.json").read_text(encoding="utf-8")
        )
        rels = [r for rs in chains["chains"].values() for r in rs]
        svc.lookup(sorted({r["caller"] for r in rels}))
        witnesses = {
            r["id"]: scoring.stored_text_has_witness(
                r, svc.chunks(r["caller"], adapter._source_label)
            )
            for r in rels
        }
    record["witnesses_in_stored_text"] = witnesses
    after = svc.generation_state()
    record["generation_before"], record["generation_after"] = before, after
    ok = (
        before == after
        and record["c3_scan"]["clean"]
        and (witnesses is None or all(witnesses.values()))
    )
    record["preflight_pass"] = ok
    write_record(Path(args.out), record)
    if not ok:
        print("PREFLIGHT FAILED: the run must not start (§7.1)")
        return 2
    return 0


def cmd_run_e2e(args) -> int:
    set_dir = Path(args.set)
    set_name, questions, qsha = load_set(set_dir, args.questions_sha256)
    check_inputs(set_name, args.repo_id, args.generation)
    refuse_sealed_present(set_name, set_dir)
    pre = json.loads(Path(args.preflight).read_text(encoding="utf-8"))
    if not pre.get("preflight_pass") or pre.get("generation") != args.generation:
        raise SystemExit("a passing preflight record for this generation is required")
    svc, qvec = _services(args)
    adapter = import_adapter()
    before = svc.require_ready()
    record = _envelope(args, "E2E", set_name, qsha)
    record["condition"] = "E2E"
    record["preflight_sha256"] = scoring.sha256_file(Path(args.preflight))
    record["service_versions_before"] = svc.versions()
    graph = rules.graph_from_export(svc.graph_export())
    chunk_table: dict = {}
    results = {}
    for q in questions["questions"]:
        ri = rules.identify_route(q["question"], graph)
        es = (
            run_es(svc, graph, ri["handler"], adapter, chunk_table)
            if ri["code"] == "resolved"
            else None
        )
        results[q["qid"]] = {
            "question_sha256": sha256_bytes(q["question"].encode("utf-8")),
            "condition": "E2E",
            "ri": ri,
            "entry": ri["handler"],
            "es": es,
            "es_fingerprint": es_fingerprint(es),
            "a0": run_a0(args, q["question"], qvec)
            if set_name == "primary"
            else {"status": "not run (owner decision P4: no stored query vector)"},
        }
    record["results"] = results
    record["chunks"] = chunk_table
    record["search_by_doc_full_pages"] = svc.full_pages
    after = svc.generation_state()
    record["service_versions_after"] = svc.versions()
    record["generation_before"], record["generation_after"] = before, after
    record["generation_unchanged"] = before == after
    write_record(Path(args.out), record)
    return 0 if before == after else 3


def cmd_run_oracle(args) -> int:
    set_dir = Path(args.set)
    set_name, questions, qsha = load_set(set_dir, args.questions_sha256)
    check_inputs(set_name, args.repo_id, args.generation)
    e2e = scoring.load_verified(Path(args.e2e), args.e2e_sha256)
    oracle = scoring.load_verified(Path(args.oracle), args.oracle_sha256)
    if e2e["stage"] != "E2E" or e2e["generation"] != args.generation:
        raise SystemExit("E2E record does not match this run")
    if e2e["code"]["sha256"]["rules"] != code_identity()["sha256"]["rules"]:
        raise SystemExit("selection rules changed since the E2E freeze (C9)")
    if set(oracle) - {"set", "entry_points"}:
        raise SystemExit("oracle file may hold entry points only (§5b)")
    svc, _ = _services(args)
    adapter = import_adapter()
    before = svc.require_ready()
    record = _envelope(args, "ORACLE-ENTRY", set_name, qsha)
    record["condition"] = "ORACLE-ENTRY"
    record["label"] = "ORACLE-ENTRY: never an end-to-end result (§5b, C12)"
    record["e2e_record_sha256"] = args.e2e_sha256
    record["oracle_file_sha256"] = args.oracle_sha256
    graph = rules.graph_from_export(svc.graph_export())
    chunk_table: dict = {}
    results = {}
    for q in questions["questions"]:
        entry = oracle["entry_points"].get(q["qid"])
        in_graph = bool(entry) and entry in graph.nodes
        es = run_es(svc, graph, entry, adapter, chunk_table) if in_graph else None
        e2e_q = e2e["results"][q["qid"]]
        same = e2e_q["entry"] is not None and e2e_q["entry"] == entry
        results[q["qid"]] = {
            "condition": "ORACLE-ENTRY",
            "entry": entry,
            "entry_in_graph": in_graph,
            "es": es,
            "es_fingerprint": es_fingerprint(es),
            "consistency": {
                "ri_handler_equals_oracle": same,
                "es_identical": (es_fingerprint(es) == e2e_q["es_fingerprint"])
                if same
                else None,
            },
        }
    record["results"] = results
    record["chunks"] = chunk_table
    record["search_by_doc_full_pages"] = svc.full_pages
    after = svc.generation_state()
    record["generation_before"], record["generation_after"] = before, after
    record["generation_unchanged"] = before == after
    write_record(Path(args.out), record)
    return 0 if before == after else 3


def _score_es(rels, es, chunks, extra_edges, index_has) -> dict:
    out = {}
    for arm, body in es.items():
        disc = body["discovery"]
        edges = disc["edges_used"] + extra_edges
        sel = scoring.selection_metrics(rels, disc["functions"])
        out[arm] = {
            "discovery": {
                "functions": len(disc["functions"]),
                "suppressed": disc["suppressed_count"],
                "cap_hit": disc["cap_hit"],
                "ambiguous": disc["ambiguous"],
            },
            "selection": sel,
            "units": {},
        }
        for unit, u in body["units"].items():
            requested = [chunks[c] for c in u["requested_chunk_ids"]]
            per_b, surv = {}, {}
            for b in BUDGETS:
                d = u["delivered"][str(b)]
                delivered = [chunks[c] for c in d["chunk_ids"]]
                per_b[b] = scoring.score_delivery(
                    rels, delivered, requested, disc["functions"], edges, index_has
                )
                surv[b] = scoring.survival_metrics(rels, delivered, d["bytes"])
            out[arm]["units"][unit] = {
                "requested_passages": len(requested),
                "requested_bytes": u["requested_bytes"],
                **{str(b): {"survival": surv[b], **per_b[b]} for b in BUDGETS},
                "budget_attribution": scoring.budget_attribution(
                    per_b[BUDGETS[0]],
                    per_b[BUDGETS[1]],
                    surv[BUDGETS[0]],
                    surv[BUDGETS[1]],
                ),
            }
    return out


def _mark_es(scores: dict | None) -> None:
    """Not-evaluable question: official sufficiency in every arm, unit and
    budget becomes NOT_EVALUABLE; the computed value and all findings stay."""
    for arm in (scores or {}).values():
        for unit in arm["units"].values():
            for b in BUDGETS:
                unit[str(b)] = scoring.mark_not_evaluable(unit[str(b)])


def cmd_score(args) -> int:  # noqa: C901 - one linear scoring pass
    set_dir = Path(args.set)
    set_name, questions, qsha = load_set(set_dir, args.questions_sha256)
    check_inputs(set_name, args.repo_id, args.generation)
    chains = scoring.load_verified(Path(args.chains), args.chains_sha256)
    e2e = scoring.load_verified(Path(args.e2e), args.e2e_sha256)
    orc = scoring.load_verified(Path(args.oracle_record), args.oracle_record_sha256)
    if orc["e2e_record_sha256"] != args.e2e_sha256:
        raise SystemExit("oracle record was not run against this E2E record")
    svc, _ = _services(args)
    adapter = import_adapter()
    svc.require_ready()
    record = _envelope(args, "score", set_name, qsha)
    record["inputs"] = {
        "chains_sha256": args.chains_sha256,
        "e2e_sha256": args.e2e_sha256,
        "oracle_record_sha256": args.oracle_record_sha256,
    }
    record["c3_rescan_with_revealed_terms"] = scoring.c3_scan(
        RULES_FILE.read_text(encoding="utf-8"),
        scoring.forbidden_terms(chains, questions),
    )
    record["rules_unchanged_across_stages"] = (
        e2e["code"]["sha256"]["rules"] == orc["code"]["sha256"]["rules"]
    )
    per_q = {}
    for q in questions["questions"]:
        qid = q["qid"]
        rels = chains["chains"][qid]
        callers = sorted({r["caller"] for r in rels})
        svc.lookup(callers)
        caller_chunks = {c: svc.chunks(c, adapter._source_label) for c in callers}
        index_has = {
            r["id"]: scoring.stored_text_has_witness(r, caller_chunks[r["caller"]])
            for r in rels
        }
        source_check = {}
        if args.source_repo:  # required by the parser; checked again here
            for r in rels:
                path = r["caller"].split("#", 1)[0]
                text = subprocess.run(
                    [
                        "git",
                        "-C",
                        args.source_repo,
                        "show",
                        f"{questions['source_commit']}:{path}",
                    ],
                    capture_output=True,
                    text=True,
                    encoding="utf-8",
                ).stdout
                source_check[r["id"]] = scoring.source_has_witness(r, text)
        status = scoring.question_status(rels, index_has, source_check)
        e_q, o_q = e2e["results"][qid], orc["results"][qid]
        oracle_entry = o_q["entry"]
        ri = e_q["ri"]
        ri_eval = {
            "code": ri["code"],
            "handler": ri["handler"],
            "oracle_handler": oracle_entry,
            "ri_error_wrong_handler": ri["code"] == "resolved"
            and ri["handler"] != oracle_entry,
        }
        ri_edges = ri.get("edges_used", [])
        e2e_scores = (
            _score_es(rels, e_q["es"], e2e["chunks"], ri_edges, index_has)
            if e_q["es"]
            else None
        )
        orc_scores = (
            _score_es(rels, o_q["es"], orc["chunks"], [], index_has)
            if o_q["es"]
            else None
        )
        end_to_end = {}
        if e2e_scores:
            for arm, a in e2e_scores.items():
                for unit, u in a["units"].items():
                    for b in BUDGETS:
                        end_to_end[f"{arm}/{unit}/{b}"] = (
                            ri["code"] == "resolved"
                            and u[str(b)]["sufficiency"] == "PASS"
                        )
        a0 = e_q.get("a0") or {}
        a0_scores = None
        if "delivered" in a0:
            a0_scores = {}
            pool = [a0["chunks"][c] for c in a0["pool_chunk_ids"]]
            for b in BUDGETS:
                delivered = [
                    a0["chunks"][c] for c in a0["delivered"][str(b)]["chunk_ids"]
                ]
                a0_scores[str(b)] = {
                    "survival": scoring.survival_metrics(
                        rels, delivered, a0["delivered"][str(b)]["bytes"]
                    ),
                    **scoring.score_delivery(
                        rels, delivered, pool, a0["functions"], [], index_has
                    ),
                }
        if status["status"] == scoring.PREFLIGHT_FAILURE:
            _mark_es(e2e_scores)
            _mark_es(orc_scores)
            if a0_scores:
                a0_scores = {
                    b: scoring.mark_not_evaluable(v) for b, v in a0_scores.items()
                }
            end_to_end = dict.fromkeys(end_to_end, "not_evaluable")
        per_q[qid] = {
            "status": status,
            "ri": ri_eval,
            "witness_recheck": {
                "stored_text": index_has,
                "pinned_source": source_check or None,
            },
            "E2E": e2e_scores,
            "end_to_end_success": end_to_end,
            "ORACLE-ENTRY": {
                "label": "ORACLE-ENTRY: excluded from every end-to-end count (C12)",
                "scores": orc_scores,
                "consistency": o_q["consistency"],
            },
            "A0": a0_scores or a0.get("status"),
            "minimum_evidence_bound": [
                scoring.minimum_evidence_bound(rels, caller_chunks, s)
                for s in (False, True)
            ],
        }
    record["results"] = per_q
    record["official_summary"] = scoring.official_summary(per_q)
    write_record(Path(args.out), record)
    return 0 if record["c3_rescan_with_revealed_terms"]["clean"] else 4


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description=(__doc__ or "").split("\n\n")[0])
    sub = p.add_subparsers(dest="cmd", required=True)

    def common(sp):
        sp.add_argument(
            "--set", required=True, help="set directory with questions.json"
        )
        sp.add_argument(
            "--questions-sha256", help="as posted on #359 (required unless primary)"
        )
        sp.add_argument("--host", required=True, help="scheme://host of the services")
        sp.add_argument("--repo-id", required=True)
        sp.add_argument("--generation", required=True)
        sp.add_argument(
            "--query-vector-file", required=True, help="§3 stored Step 0 vector"
        )
        sp.add_argument("--out", required=True)

    common(sp := sub.add_parser("preflight"))
    sp.set_defaults(fn=cmd_preflight)
    common(sp := sub.add_parser("run-e2e"))
    sp.add_argument("--preflight", required=True)
    sp.set_defaults(fn=cmd_run_e2e)
    common(sp := sub.add_parser("run-oracle"))
    sp.add_argument("--e2e", required=True)
    sp.add_argument("--e2e-sha256", required=True)
    sp.add_argument("--oracle", required=True)
    sp.add_argument("--oracle-sha256", required=True)
    sp.set_defaults(fn=cmd_run_oracle)
    common(sp := sub.add_parser("score"))
    sp.add_argument("--chains", required=True)
    sp.add_argument("--chains-sha256", required=True)
    sp.add_argument("--e2e", required=True)
    sp.add_argument("--e2e-sha256", required=True)
    sp.add_argument("--oracle-record", required=True)
    sp.add_argument("--oracle-record-sha256", required=True)
    sp.add_argument(
        "--source-repo",
        required=True,
        help="git checkout holding the pinned source commit (P3 source check)",
    )
    sp.set_defaults(fn=cmd_score)
    args = p.parse_args(argv)
    return args.fn(args)


if __name__ == "__main__":
    sys.exit(main())
