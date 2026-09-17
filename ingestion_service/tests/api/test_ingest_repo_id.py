# ingestion_service/tests/api/test_ingest_repo_id.py
"""#166: repo_id is computed at HTTP accept time (before any clone) and
threaded through to submit_ingestion, independent of document_nodes.
"""
from unittest.mock import MagicMock, patch

import pytest

from src.api.v1 import codebase_ingest
from src.core.codebase.identity import build_repo_id
from src.core.ingestion_ownership import RepositoryBusy

pytestmark = pytest.mark.unit


def test_ingest_repo_passes_deterministic_repo_id_to_submit_ingestion():
    mock_submit = MagicMock()
    with patch.object(codebase_ingest, "submit_ingestion", mock_submit):
        codebase_ingest.ingest_repo(git_url="https://example.com/a.git")

    assert mock_submit.call_count == 1
    assert mock_submit.call_args.kwargs["repo_id"] == build_repo_id(
        "https://example.com/a.git",
    )


def test_ingest_repo_same_url_always_yields_same_repo_id():
    mock_submit = MagicMock()
    with patch.object(codebase_ingest, "submit_ingestion", mock_submit):
        codebase_ingest.ingest_repo(git_url="https://example.com/b.git")
        codebase_ingest.ingest_repo(git_url="https://example.com/b.git")

    first, second = (c.kwargs["repo_id"] for c in mock_submit.call_args_list)
    assert first == second


def test_repository_busy_maps_to_409_retryable():
    with patch.object(
        codebase_ingest, "submit_ingestion",
        MagicMock(side_effect=RepositoryBusy("repo is being deleted")),
    ):
        with pytest.raises(codebase_ingest.HTTPException) as exc_info:
            codebase_ingest.ingest_repo(git_url="https://example.com/c.git")

    assert exc_info.value.status_code == 409
    assert exc_info.value.headers["Retry-After"] == "5"
