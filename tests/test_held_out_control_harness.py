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
