"""The frozen evaluator can select per-request arms without changing defaults."""

import argparse
import importlib.util
from pathlib import Path


MODULE_PATH = Path(__file__).resolve().parents[1] / "scripts/issue240_overview_eval.py"
SPEC = importlib.util.spec_from_file_location("issue240_overview_eval", MODULE_PATH)
assert SPEC is not None and SPEC.loader is not None
evaluation = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(evaluation)


def test_cli_controls_preserve_omitted_and_exact_candidate_values():
    assert evaluation.control_overrides(argparse.Namespace(
        claim_selection="inherit", structured_answers="inherit",
        canonical_selection="inherit",
    )) == {}
    assert evaluation.control_overrides(argparse.Namespace(
        claim_selection="on", structured_answers="on",
        canonical_selection="off",
    )) == {
        "repository_overview_claim_selection_enabled": True,
        "repository_overview_structured_answers_enabled": True,
        "repository_overview_canonical_selection_enabled": False,
    }


def test_case_sends_controls_and_keeps_frozen_query(monkeypatch):
    sent = []
    lineage = {"ingestion_id": "g1", "commit_sha": "sha"}
    monkeypatch.setattr(evaluation, "generation", lambda *_args: lineage)

    def fetch(_url, request, timeout):
        sent.append(request)
        return {"repo_id": "r1", "retrieval_plan": {"generation_id": "g1"},
                "answer": "ok", "sources": []}

    monkeypatch.setattr(evaluation, "fetch", fetch)
    controls = {"repository_overview_structured_answers_enabled": True}
    result = evaluation.run_case(
        "http://orchestrator", "http://ingestion",
        evaluation.CASES[0], "r1", "g1", "sha", controls,
    )
    assert sent[0]["query"] == evaluation.CASES[0][1]
    assert sent[0]["claim_type"] == "repository_overview"
    assert sent[0]["repository_overview_structured_answers_enabled"] is True
    assert result["request"] == sent[0]
