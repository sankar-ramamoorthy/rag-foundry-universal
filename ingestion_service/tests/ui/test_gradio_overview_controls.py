"""Gradio sends query mode and independent overview controls per request."""

from unittest.mock import MagicMock, patch

import pytest

from src.ui.gradio_app import build_ui, submit_rag_query


pytestmark = pytest.mark.unit


def _sent_payload(*args):
    response = MagicMock()
    response.json.return_value = {"answer": "ok", "sources": []}
    with patch("src.ui.gradio_app.requests.post", return_value=response) as post:
        answer = submit_rag_query("question", "repo-1", 10, None, None, *args)
    assert "ok" in answer
    return post.call_args.kwargs["json"]


def test_normal_mode_defaults_to_off_and_omits_claim_type():
    payload = _sent_payload()
    assert "claim_type" not in payload
    assert payload["repository_overview_claim_selection_enabled"] is False
    assert payload["repository_overview_structured_answers_enabled"] is False
    assert payload["repository_overview_canonical_selection_enabled"] is False


def test_overview_mode_sends_exact_frozen_candidate_combination():
    payload = _sent_payload("repository_overview", True, True, False)
    assert payload["claim_type"] == "repository_overview"
    assert payload["repository_overview_claim_selection_enabled"] is True
    assert payload["repository_overview_structured_answers_enabled"] is True
    assert payload["repository_overview_canonical_selection_enabled"] is False


def test_canonical_control_is_independent():
    payload = _sent_payload("repository_overview", False, False, True)
    assert payload["repository_overview_claim_selection_enabled"] is False
    assert payload["repository_overview_structured_answers_enabled"] is False
    assert payload["repository_overview_canonical_selection_enabled"] is True


def test_overview_answer_shows_server_confirmed_effective_controls():
    response = MagicMock()
    response.json.return_value = {
        "answer": "repo answer", "sources": [],
        "retrieval_plan": {"repository_overview_controls": {
            "claim_selection_enabled": True,
            "structured_answers_enabled": True,
            "canonical_selection_enabled": False,
        }},
    }
    with patch("src.ui.gradio_app.requests.post", return_value=response):
        output = submit_rag_query(
            "question", "repo-1", 10, None, None,
            "repository_overview", True, True, False,
        )
    assert "claim selection True" in output
    assert "structured answers True" in output
    assert "canonical selection False" in output


def test_overview_answer_discloses_missing_server_confirmation():
    response = MagicMock()
    response.json.return_value = {"answer": "repo answer", "sources": []}
    with patch("src.ui.gradio_app.requests.post", return_value=response):
        output = submit_rag_query(
            "question", "repo-1", 10, None, None, "repository_overview"
        )
    assert "server confirmation unavailable" in output


def test_ui_controls_default_off_and_feed_rag_callback():
    ui = build_ui()
    components = {
        item["id"]: item["props"] for item in ui.config["components"]
    }
    expected = {
        "Query mode": "normal",
        "Overview claim selection": False,
        "Structured repository answers": False,
        "Canonical source selection": False,
    }
    for label, value in expected.items():
        assert any(
            props.get("label") == label and props.get("value") == value
            for props in components.values()
        )
    rag_handler = next(
        item for item in ui.config["dependencies"]
        if item.get("api_name") == "submit_rag_query"
    )
    connected = {components[item].get("label") for item in rag_handler["inputs"]}
    assert set(expected).issubset(connected)
