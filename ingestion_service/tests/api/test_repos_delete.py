# ingestion_service/tests/api/test_repos_delete.py
"""
Issue #158: DELETE /v1/repos/{repo_id} — hard delete a repo's vectors,
graph nodes/relationships, and ingestion_requests records.

Unit-level: db_utils, HttpVectorStore, and CodebaseGraphPersistence are
all mocked out, so these exercise only the route's own orchestration
logic (order of operations, idempotency, partial-failure handling) —
not real DB/HTTP behavior. See test_atomic_graph_persistence.py (docker
+ integration marker) for the real-DB equivalent of delete_repo_nodes,
and this issue's follow-up for an integration test covering the new
db_utils helpers end to end.
"""
import asyncio
from unittest.mock import MagicMock, patch

import pytest
from fastapi import HTTPException

from src.api.v1.repos import delete_repo

pytestmark = pytest.mark.unit


def _run(coro):
    return asyncio.run(coro)


@pytest.fixture(autouse=True)
def _repo_lock_granted():
    """#166: delete_repo now takes the repo-scope advisory lock and checks
    for an active ingestion before doing anything else. These ordering/
    idempotency tests are about what happens after that guard passes, so
    grant it unconditionally here rather than repeating the same two
    patches in every test.
    """
    guard = MagicMock()
    with patch(
        "src.api.v1.repos.reserve_repo_mutation", MagicMock(return_value=guard),
    ), patch("src.api.v1.repos.get_engine", MagicMock()):
        yield guard


class TestDeleteRepoIdempotency:
    @patch("src.api.v1.repos.db_utils")
    def test_no_ingestion_ids_returns_not_found_without_touching_anything(
        self, mock_db_utils
    ):
        """Calling delete on an already-deleted (or never-existed) repo_id
        must be a safe no-op, not an error — issue #158's idempotency
        requirement."""
        mock_db_utils.has_active_ingestion_for_repo.return_value = False
        mock_db_utils.list_ingestion_ids_for_repo.return_value = []

        result = _run(delete_repo("nonexistent-repo"))

        assert result.status == "not_found"
        assert result.ingestion_ids == []
        assert result.nodes_deleted == 0
        assert result.ingestion_requests_deleted == 0
        mock_db_utils.delete_ingestion_requests.assert_not_called()


class TestDeleteRepoLock:
    @patch("src.api.v1.repos.get_engine", MagicMock())
    def test_repo_busy_returns_409(self):
        """A concurrent ingest (or another delete) holding the repo-scope
        lock must reject this delete with a retryable 409, not race it."""
        from src.core.ingestion_ownership import RepositoryBusy

        with patch(
            "src.api.v1.repos.reserve_repo_mutation",
            MagicMock(side_effect=RepositoryBusy("busy")),
        ):
            with pytest.raises(HTTPException) as exc_info:
                _run(delete_repo("repo-abc"))
        assert exc_info.value.status_code == 409
        assert exc_info.value.headers["Retry-After"] == "5"

    @patch("src.api.v1.repos.db_utils")
    def test_active_ingestion_returns_409_and_releases_lock(
        self, mock_db_utils, _repo_lock_granted,
    ):
        """An active accepted/running ingestion for this repo_id must block
        delete outright rather than deleting out from under a live worker."""
        mock_db_utils.has_active_ingestion_for_repo.return_value = True

        with pytest.raises(HTTPException) as exc_info:
            _run(delete_repo("repo-abc"))

        assert exc_info.value.status_code == 409
        mock_db_utils.list_ingestion_ids_for_repo.assert_not_called()
        _repo_lock_granted.close.assert_called_once()


class TestDeleteRepoOrdering:
    @patch("src.api.v1.repos.CodebaseGraphPersistence")
    @patch("src.api.v1.repos.HttpVectorStore")
    @patch("src.api.v1.repos.get_settings")
    @patch("src.api.v1.repos.db_utils")
    def test_happy_path_deletes_in_order_vectors_nodes_then_requests_last(
        self, mock_db_utils, mock_get_settings, mock_http_vs_cls, mock_persistence_cls
    ):
        """The order is load-bearing (issue #158): ingestion_requests rows
        must not be deleted until vector and graph cleanup have both
        succeeded, since they're the retry's only way to rediscover what
        needs cleaning up."""
        mock_db_utils.has_active_ingestion_for_repo.return_value = False
        mock_db_utils.list_ingestion_ids_for_repo.return_value = ["ing-1", "ing-2"]
        mock_db_utils.delete_ingestion_requests.return_value = 2

        mock_vs = MagicMock()
        mock_http_vs_cls.return_value = mock_vs

        mock_persistence = MagicMock()
        mock_persistence.delete_repo_nodes.return_value = 42
        mock_persistence_cls.return_value = mock_persistence

        calls = []
        mock_vs.delete_by_ingestion_id.side_effect = (
            lambda iid: calls.append(("vector", iid))
        )
        mock_persistence.delete_repo_nodes.side_effect = (
            lambda repo_id: calls.append(("nodes", repo_id)) or 42
        )
        mock_db_utils.delete_ingestion_requests.side_effect = (
            lambda ids: calls.append(("requests", tuple(ids))) or len(ids)
        )

        result = _run(delete_repo("repo-abc"))

        assert result.status == "deleted"
        assert result.ingestion_ids == ["ing-1", "ing-2"]
        assert result.nodes_deleted == 42
        assert result.ingestion_requests_deleted == 2

        # vectors for every enumerated ingestion_id, then nodes, then
        # ingestion_requests -- in that order, requests strictly last.
        assert calls == [
            ("vector", "ing-1"),
            ("vector", "ing-2"),
            ("nodes", "repo-abc"),
            ("requests", ("ing-1", "ing-2")),
        ]

    @patch("src.api.v1.repos.CodebaseGraphPersistence")
    @patch("src.api.v1.repos.HttpVectorStore")
    @patch("src.api.v1.repos.get_settings")
    @patch("src.api.v1.repos.db_utils")
    def test_vector_cleanup_failure_leaves_ingestion_requests_untouched(
        self, mock_db_utils, mock_get_settings, mock_http_vs_cls, mock_persistence_cls
    ):
        """Partial failure at the vector step: nothing downstream (graph,
        ingestion_requests) should be touched, so a retry starts clean."""
        mock_db_utils.has_active_ingestion_for_repo.return_value = False
        mock_db_utils.list_ingestion_ids_for_repo.return_value = ["ing-1"]

        mock_vs = MagicMock()
        mock_vs.delete_by_ingestion_id.side_effect = RuntimeError("vector store down")
        mock_http_vs_cls.return_value = mock_vs

        with pytest.raises(HTTPException) as exc_info:
            _run(delete_repo("repo-abc"))

        assert exc_info.value.status_code == 502
        mock_persistence_cls.assert_not_called()
        mock_db_utils.delete_ingestion_requests.assert_not_called()

    @patch("src.api.v1.repos.CodebaseGraphPersistence")
    @patch("src.api.v1.repos.HttpVectorStore")
    @patch("src.api.v1.repos.get_settings")
    @patch("src.api.v1.repos.db_utils")
    def test_graph_cleanup_failure_leaves_ingestion_requests_untouched(
        self, mock_db_utils, mock_get_settings, mock_http_vs_cls, mock_persistence_cls
    ):
        """Partial failure at the graph step (vectors already deleted):
        ingestion_requests must still survive for the retry, since it's
        the only remaining record of which ingestion_ids to re-check."""
        mock_db_utils.has_active_ingestion_for_repo.return_value = False
        mock_db_utils.list_ingestion_ids_for_repo.return_value = ["ing-1"]

        mock_vs = MagicMock()
        mock_http_vs_cls.return_value = mock_vs

        mock_persistence = MagicMock()
        mock_persistence.delete_repo_nodes.side_effect = RuntimeError("db error")
        mock_persistence_cls.return_value = mock_persistence

        with pytest.raises(HTTPException) as exc_info:
            _run(delete_repo("repo-abc"))

        assert exc_info.value.status_code == 500
        mock_db_utils.delete_ingestion_requests.assert_not_called()
