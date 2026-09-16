# ingestion_service/tests/ui/test_gradio_delete_repo.py
"""
Issue #162: Gradio's delete_repo() callback wraps DELETE
/v1/repos/{repo_id} (issue #158/PR #159). These tests cover the
callback's own logic only — confirmation gating, error surfacing, and
idempotent "not_found" handling — not the endpoint itself, which has
its own tests in ingestion_service/tests/api.
"""
from unittest.mock import MagicMock, patch

import pytest

from src.ui.gradio_app import delete_repo

pytestmark = pytest.mark.unit


def test_delete_repo_requires_a_selection():
    message, _ = delete_repo(None, True)
    assert "select a repository" in message.lower()


def test_delete_repo_requires_confirmation():
    with patch("src.ui.gradio_app.requests") as mock_requests:
        message, _ = delete_repo("repo-123", False)

    assert "confirm delete" in message.lower()
    mock_requests.delete.assert_not_called()


def test_delete_repo_success_calls_endpoint_and_refreshes_list():
    delete_response = MagicMock()
    delete_response.json.return_value = {
        "status": "deleted",
        "repo_id": "repo-123",
        "ingestion_ids": ["ing-1", "ing-2"],
        "nodes_deleted": 42,
        "ingestion_requests_deleted": 2,
    }
    refresh_response = MagicMock()
    refresh_response.json.return_value = []  # no repos left after deletion

    with patch("src.ui.gradio_app.requests") as mock_requests:
        mock_requests.delete.return_value = delete_response
        mock_requests.get.return_value = refresh_response

        message, dropdown = delete_repo("repo-123", True)

    mock_requests.delete.assert_called_once()
    called_url = mock_requests.delete.call_args[0][0]
    assert called_url.endswith("/v1/repos/repo-123")

    assert "deleted" in message.lower()
    assert "42" in message
    # refresh_repos() ran and found nothing left
    assert dropdown.choices == []


def test_delete_repo_not_found_is_reported_not_treated_as_error():
    delete_response = MagicMock()
    delete_response.json.return_value = {
        "status": "not_found",
        "repo_id": "repo-123",
        "ingestion_ids": [],
        "nodes_deleted": 0,
        "ingestion_requests_deleted": 0,
    }
    refresh_response = MagicMock()
    refresh_response.json.return_value = []

    with patch("src.ui.gradio_app.requests") as mock_requests:
        mock_requests.delete.return_value = delete_response
        mock_requests.get.return_value = refresh_response

        message, _ = delete_repo("repo-123", True)

    assert "already gone" in message.lower()


def test_delete_repo_surfaces_backend_errors():
    with patch("src.ui.gradio_app.requests") as mock_requests:
        mock_requests.delete.side_effect = RuntimeError("connection refused")

        message, _ = delete_repo("repo-123", True)

    assert "delete failed" in message.lower()
    assert "connection refused" in message
