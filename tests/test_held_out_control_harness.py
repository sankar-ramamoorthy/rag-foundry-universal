"""Held-out control harness (#317): offline tests of its pure logic.

No network and no production access. The harness replays the 12 frozen
held-out cases through the unchanged runtime; these tests cover only what it
decides before and after a query: preflight, the named/not-named split, what is
delivered or in the pool, run-to-run reproducibility, and overwrite refusal.
"""

import copy
import importlib.util
import json
import shutil
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
HELD_OUT = ROOT / "DOCS/evaluations/code-evidence-held-out"
SPEC = importlib.util.spec_from_file_location(
    "held_out_control", ROOT / "scripts/held_out_control.py"
)
hc = importlib.util.module_from_spec(SPEC)
sys.modules["held_out_control"] = hc
SPEC.loader.exec_module(hc)

NAMED = {"H1", "H2", "H3", "P1", "P2", "P3", "W2", "W3"}
NOT_NAMED = {"H4", "P4", "W1", "W4"}


def _inputs():
    return hc.load_inputs(HELD_OUT)


def test_static_preflight_passes_on_the_frozen_inputs():
    inputs = _inputs()
    assert len(inputs.cases) == 12
    assert {c["repo"] for c in inputs.cases} == set(inputs.pin["repositories"])


def test_preflight_refuses_a_changed_manifest(tmp_path):
    for name in ("manifest.json", "manifest.sha256", "held-out-corpus-pin.json"):
        shutil.copy(HELD_OUT / name, tmp_path / name)
    text = (tmp_path / "manifest.json").read_text(encoding="utf-8")
    (tmp_path / "manifest.json").write_text(text + " ", encoding="utf-8")
    with pytest.raises(hc.HarnessError, match="manifest"):
        hc.load_inputs(tmp_path)


def _ready(entry):
    return {
        "repo_id": entry["repo_id"],
        "ingestion_id": entry["ingestion_id"],
        "generation_status": "ready",
        "commit_sha": entry["source"]["recorded_commit"],
        "is_incremental": False,
    }


@pytest.mark.parametrize(
    "change",
    [
        {"generation_status": "building"},
        {"ingestion_id": "00000000-0000-0000-0000-000000000000"},
        {"commit_sha": "0" * 40},
        {"is_incremental": True},
    ],
    ids=["not-ready", "wrong-ingestion", "wrong-commit", "incremental"],
)
def test_generation_preflight_refuses_a_mismatched_generation(change):
    entry = _inputs().pin["repositories"]["pypa/hatch"]
    hc.check_generation(entry, _ready(entry))  # the matching one passes
    with pytest.raises(hc.HarnessError):
        hc.check_generation(entry, {**_ready(entry), **change})


def test_settings_preflight_matches_the_execution_contract_and_refuses_drift():
    contract = _inputs().contract
    hc.check_settings(contract, dict(hc.RUN_SETTINGS))
    for key, bad in (("top_k", 21), ("max_total_tokens", 8192), ("rerank", True)):
        with pytest.raises(hc.HarnessError):
            hc.check_settings(contract, {**hc.RUN_SETTINGS, key: bad})


def test_named_split_equals_the_preregistered_mechanical_rule():
    cases = {c["id"]: c for c in _inputs().cases}
    assert {i for i, c in cases.items() if hc.is_named(c)} == NAMED
    assert {i for i, c in cases.items() if not hc.is_named(c)} == NOT_NAMED


def _chunk(canonical_id, text="x"):
    return {"canonical_id": canonical_id, "text": text}


def _record(case, final, pool, context="ctx"):
    return {
        "final_chunks": final,
        "pre_budget_chunks": pool,
        "assembled_context": context,
    }


def test_summarize_reports_delivered_in_pool_and_context_hash():
    case = _inputs().cases[0]
    primary = case["primary_function"]
    delivered = hc.summarize_record(
        case, _record(case, [_chunk(primary)], [_chunk(primary)], "abc")
    )
    assert delivered["primary_delivered"] and delivered["primary_in_pool"]
    assert delivered["context_sha256"] == hc.sha256_text("abc")
    assert delivered["context_bytes"] == 3

    lost = hc.summarize_record(
        case, _record(case, [_chunk("other.py#f")], [_chunk(primary)])
    )
    assert not lost["primary_delivered"] and lost["primary_in_pool"]

    absent = hc.summarize_record(case, _record(case, [], [_chunk("other.py#f")]))
    assert not absent["primary_delivered"] and not absent["primary_in_pool"]


def test_summarize_never_invents_a_pool_when_none_was_captured():
    case = _inputs().cases[0]
    record = _record(case, [_chunk(case["primary_function"])], None)
    record.pop("pre_budget_chunks")
    assert hc.summarize_record(case, record)["primary_in_pool"] is None


def test_compare_runs_reports_reproduction_and_every_difference():
    one = {"H1": {"context_sha256": "a"}, "H2": {"context_sha256": "b"}}
    same = copy.deepcopy(one)
    assert hc.compare_runs(one, same) == {
        "reproduced": True,
        "per_case": {"H1": True, "H2": True},
        "differing_cases": [],
    }
    other = {"H1": {"context_sha256": "a"}, "H2": {"context_sha256": "c"}}
    result = hc.compare_runs(one, other)
    assert result["reproduced"] is False and result["differing_cases"] == ["H2"]
    with pytest.raises(hc.HarnessError):
        hc.compare_runs(one, {"H1": {"context_sha256": "a"}})


def test_a_completed_capture_is_never_overwritten(tmp_path):
    path = tmp_path / "held-out-control-run1-H1.json"
    hc.write_capture(path, {"a": 1})
    with pytest.raises(FileExistsError):
        hc.write_capture(path, {"a": 2})
    assert json.loads(path.read_text(encoding="utf-8")) == {"a": 1}


def test_the_plan_lists_all_twelve_cases_and_run_names_without_network():
    inputs = _inputs()
    lines = hc.plan_lines(inputs, runs=2)
    text = "\n".join(lines)
    for case in inputs.cases:
        assert case["id"] in text
    assert "run1" in text and "run2" in text
    assert text.count("named") >= 12


def test_the_harness_adds_no_default_address():
    source = (ROOT / "scripts/held_out_control.py").read_text(encoding="utf-8")
    import re

    assert not re.search(r"\b\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3}\b", source)


# --- review additions (PR #320): boundary, preflight/run split, API drift ---


def _record_ok(context="ctx", plan_tokens=3):
    return {
        "final_chunks": [{"canonical_id": "a.py#f", "text": "x"}],
        "pre_budget_chunks": [{"canonical_id": "a.py#f", "text": "x"}],
        "assembled_context": context,
        "response": {"retrieval_plan": {"tokens_after_budget": plan_tokens}},
    }


def test_validate_record_accepts_a_complete_consistent_record():
    hc.validate_record(_record_ok(), cap=4096)


@pytest.mark.parametrize(
    "mutate",
    [
        lambda r: r.pop("final_chunks"),
        lambda r: r.pop("pre_budget_chunks"),
        lambda r: r.pop("assembled_context"),
        lambda r: r.update(assembled_context=""),
        lambda r: r.pop("response"),
        lambda r: r["response"]["retrieval_plan"].update(tokens_after_budget=99),
        lambda r: r.update(assembled_context="x" * 5000),
    ],
    ids=[
        "no-final-chunks",
        "no-pool",
        "no-context",
        "empty-context",
        "no-response",
        "plan-bytes-disagree",
        "over-cap",
    ],
)
def test_validate_record_rejects_incomplete_or_inconsistent_records(mutate):
    record = _record_ok()
    mutate(record)
    with pytest.raises(hc.HarnessError):
        hc.validate_record(record, cap=4096)


def test_incomplete_capture_is_recorded_without_overwriting(tmp_path, monkeypatch):
    monkeypatch.setattr(hc, "RAW", tmp_path)
    path = hc.write_incomplete(1, "H1", {"partial": True}, "boom")
    assert path.name == "held-out-control-incomplete-run1-H1.json"
    data = json.loads(path.read_text(encoding="utf-8"))
    assert data["status"] == "incomplete-no-summary" and data["error"] == "boom"
    with pytest.raises(FileExistsError):
        hc.write_incomplete(1, "H1", {}, "again")


def test_rag_arguments_use_only_the_question_the_pin_and_contract_settings():
    inputs = _inputs()
    case = inputs.cases[0]
    entry = inputs.pin["repositories"][case["repo"]]
    args = hc.rag_arguments(case, entry)
    assert args["query"] == case["query"]
    assert args["repo_id"] == entry["repo_id"]
    assert args["trace_canonical_ids"] == hc.case_ids(case)
    # nothing else is derived from the manifest: the rest are fixed settings
    fixed = {k: v for k, v in args.items() if k not in
             ("query", "repo_id", "trace_canonical_ids")}
    assert fixed == {
        "top_k": 20,
        "max_chunks_per_doc": 5,
        "max_total_tokens": 4096,
        "model": hc.MODEL,
        "rerank": False,
        "repository_overview_claim_selection_enabled": False,
        "repository_overview_canonical_selection_enabled": False,
        "repository_overview_structured_answers_enabled": False,
    }


def _run_rag_parameters():
    import ast

    tree = ast.parse((ROOT / "rag_orchestrator/src/core/service.py").read_text("utf-8"))
    for node in ast.walk(tree):
        if isinstance(node, ast.AsyncFunctionDef) and node.name == "run_rag":
            return {a.arg for a in node.args.args}
    raise AssertionError("run_rag not found in the orchestrator")


def test_rag_arguments_match_the_deployed_run_rag_signature():
    inputs = _inputs()
    case = inputs.cases[0]
    args = hc.rag_arguments(case, inputs.pin["repositories"][case["repo"]])
    assert set(args) <= _run_rag_parameters()


def test_pool_capture_still_depends_on_the_unbounded_assemble_call():
    """The in-pool measurement reads the observer's pre-budget capture, which
    exists only while the orchestrator makes its unbounded assemble call."""
    source = (ROOT / "rag_orchestrator/src/core/service.py").read_text("utf-8")
    assert "assemble_context(agent_chunks, 2**63)" in source
    assert "assemble_context(agent_chunks, context_budget)" in source


def test_trace_ids_stay_observational_in_the_orchestrator():
    source = (ROOT / "rag_orchestrator/src/core/service.py").read_text("utf-8")
    block = source.split("if trace_canonical_ids:", 1)[1].split("logger.info", 1)[0]
    assert "compute_partial_evidence_survival" in block
    assert "_evidence_trace_partial" in block
    # nothing after retrieval reads the trace to choose or order chunks
    assert source.count("_evidence_trace_partial") <= 3


def test_overview_flags_are_checked_against_the_contract():
    contract = copy.deepcopy(_inputs().contract)
    hc.check_settings(contract, dict(hc.RUN_SETTINGS))
    contract["overview_flags"] = True
    with pytest.raises(hc.HarnessError):
        hc.check_settings(contract, dict(hc.RUN_SETTINGS))


def test_plan_with_host_reads_only_generation_and_version_endpoints(monkeypatch):
    urls = []

    class _Response:
        def __init__(self, payload):
            self.payload = payload

        def read(self):
            return json.dumps(self.payload).encode()

        def __enter__(self):
            return self

        def __exit__(self, *exc):
            return False

    inputs = _inputs()
    by_repo = {e["repo_id"]: e for e in inputs.pin["repositories"].values()}

    def fake_urlopen(url, timeout=None):
        url = getattr(url, "full_url", url)
        urls.append(url)
        if url.endswith("/version"):
            return _Response({"version": "test"})
        repo_id = url.split("/repos/")[1].split("/")[0]
        return _Response(_ready(by_repo[repo_id]))

    import urllib.request

    monkeypatch.setattr(urllib.request, "urlopen", fake_urlopen)
    assert hc.main(["plan", "--host", "http://example.invalid"]) == 0
    assert urls, "plan --host should perform its read-only checks"
    for url in urls:
        assert url.endswith("/generation") or url.endswith("/version"), url
        assert "/rag" not in url and "ingest" not in url


def test_run_refuses_without_the_explicit_execute_flag(monkeypatch):
    import urllib.request

    def no_network(*a, **k):
        raise AssertionError("no request may be made without the execute flag")

    monkeypatch.setattr(urllib.request, "urlopen", no_network)
    assert hc.main(["run", "--host", "http://example.invalid"]) == 1
