# ingestion_service/tests/api/test_repos_delete_async_offload.py
"""
Issue #170 (WP-R7): delete_repo is `async def` but its body -- advisory
lock acquisition, db_utils lookups, HttpVectorStore calls, and the graph
persistence session -- was entirely synchronous, running directly on the
event loop. A slow delete (large repo, contended lock, slow vector
cleanup) stalled every other request the process was handling for its
whole duration; this is the mechanism behind audit A9's recorded
production pause.

This test doesn't touch a real database -- the same collaborators
test_repos_delete.py mocks are mocked here too -- and only proves the
route no longer blocks the event loop while a slow step is in flight. See
test_repos_delete.py for correctness/ordering/idempotency coverage, which
this file does not repeat.
"""
import asyncio
import time
from unittest.mock import MagicMock, patch

import pytest

from src.api.v1.repos import delete_repo

pytestmark = pytest.mark.unit

BLOCKING_SECONDS = 0.3
HEARTBEAT_INTERVAL = 0.02
# If the blocking step ran on the event loop instead of a worker thread,
# the heartbeat couldn't tick during it at all. A healthy loop should
# manage most of the ~15 available ticks; require a majority as a
# non-flaky floor.
MIN_EXPECTED_TICKS = 8


async def _heartbeat(duration: float) -> list:
    ticks = []
    start = time.monotonic()
    while time.monotonic() - start < duration:
        ticks.append(time.monotonic())
        await asyncio.sleep(HEARTBEAT_INTERVAL)
    return ticks


async def _run_concurrently(blocking_coro):
    _, ticks = await asyncio.gather(blocking_coro, _heartbeat(BLOCKING_SECONDS))
    return ticks


@patch("src.api.v1.repos.CodebaseGraphPersistence")
@patch("src.api.v1.repos.HttpVectorStore")
@patch("src.api.v1.repos.get_settings")
@patch("src.api.v1.repos.db_utils")
@patch("src.api.v1.repos.get_engine", MagicMock())
@patch("src.api.v1.repos.reserve_repo_mutation")
def test_slow_vector_cleanup_does_not_block_event_loop(
    mock_reserve, mock_db_utils, mock_get_settings, mock_http_vs_cls,
    mock_persistence_cls,
):
    mock_reserve.return_value = MagicMock()
    mock_db_utils.has_active_ingestion_for_repo.return_value = False
    mock_db_utils.list_ingestion_ids_for_repo.return_value = ["ing-1"]
    mock_db_utils.delete_ingestion_requests.return_value = 1

    mock_vs = MagicMock()
    mock_vs.delete_by_ingestion_id.side_effect = lambda _id: time.sleep(
        BLOCKING_SECONDS
    )
    mock_http_vs_cls.return_value = mock_vs

    mock_persistence = MagicMock()
    mock_persistence.delete_repo_nodes.return_value = 0
    mock_persistence_cls.return_value = mock_persistence

    ticks = asyncio.run(_run_concurrently(delete_repo("repo-abc")))

    assert len(ticks) >= MIN_EXPECTED_TICKS
