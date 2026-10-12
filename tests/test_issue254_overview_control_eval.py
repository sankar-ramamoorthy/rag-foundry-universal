"""Reject comparisons whose corpus or effective controls are not matched."""

import importlib.util
import sys
from pathlib import Path

import pytest


SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPTS))
SPEC = importlib.util.spec_from_file_location(
    "issue254_eval", SCRIPTS / "issue254_overview_control_eval.py"
)
assert SPEC is not None and SPEC.loader is not None
evaluation = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(evaluation)
sys.path.pop(0)


@pytest.mark.parametrize("arm", evaluation.ARMS)
def test_request_arms_keep_query_and_retrieval_settings_fixed(arm):
    case = evaluation.AGENT_CASES[0]
    request = evaluation.request_for(case, "repo", arm)
    assert request["query"] == case[1]
    assert request["trace_canonical_ids"] == list(case[3])
    assert request["top_k"] == 10
    assert request["rerank"] is False
    assert (request.get("claim_type") == "repository_overview") == (arm != "normal")


@pytest.mark.parametrize("drift", ["repo", "generation", "controls", "missing"])
def test_response_drift_cannot_be_accepted_as_a_matched_result(drift):
    request = evaluation.request_for(evaluation.AGENT_CASES[0], "repo", "candidate")
    response = {
        "repo_id": "repo",
        "retrieval_plan": {
            "generation_id": "g",
            "repository_overview_controls": {
                "claim_selection_enabled": True,
                "structured_answers_enabled": True,
                "canonical_selection_enabled": False,
            },
        },
    }
    evaluation.validate_response(response, request, "g")
    if drift == "repo":
        response["repo_id"] = "other"
    elif drift == "generation":
        response["retrieval_plan"]["generation_id"] = "other"
    elif drift == "controls":
        response["retrieval_plan"]["repository_overview_controls"][
            "claim_selection_enabled"
        ] = False
    else:
        del response["retrieval_plan"]["repository_overview_controls"]
    with pytest.raises(RuntimeError):
        evaluation.validate_response(response, request, "g")
