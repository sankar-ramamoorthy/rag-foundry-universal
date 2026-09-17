# ingestion_service/tests/api/test_repo_generation.py
"""
Issue #168 (WP-R5): GET /v1/repos/{repo_id}/generation is the cheap
generation check rag_orchestrator's graph cache uses instead of a full
graph re-fetch. Unit-level: db_utils is mocked, so this exercises only the
route's response-model wiring -- see test_repo_lifecycle.py (integration
marker) for the real-Postgres behavior of resolve_current_generation/
generation_status this route wraps.
"""
import asyncio
from unittest.mock import patch

import pytest

from src.api.v1.repos import get_repo_generation

pytestmark = pytest.mark.unit


def _run(coro):
    return asyncio.run(coro)


@patch("src.api.v1.repos.db_utils")
def test_ready_generation_round_trips_ingestion_id(mock_db_utils):
    mock_db_utils.resolve_current_generation.return_value = "ing-1"
    mock_db_utils.generation_status.return_value = "ready"

    response = _run(get_repo_generation("repo-x"))

    assert response.repo_id == "repo-x"
    assert response.ingestion_id == "ing-1"
    assert response.generation_status == "ready"


@pytest.mark.parametrize("status", ["building", "failed", "unknown"])
@patch("src.api.v1.repos.db_utils")
def test_no_completed_generation_has_null_ingestion_id(mock_db_utils, status):
    mock_db_utils.resolve_current_generation.return_value = None
    mock_db_utils.generation_status.return_value = status

    response = _run(get_repo_generation("repo-x"))

    assert response.ingestion_id is None
    assert response.generation_status == status
