# vector_store_service/tests/api/test_vectors_async_offload.py
"""
Issue #170 (WP-R7): the /v1/vectors routes are `async def` but PgVectorStore
opens a synchronous psycopg connection per call. Before this fix, a slow
store call (e.g. a large delete or a contended query) ran directly on the
event loop and stalled every other request the process was handling.

These tests don't touch a real database -- PgVectorStore is replaced with
a fake whose blocking method is a plain time.sleep, standing in for a slow
synchronous DB call. Correctness (request/response shape) is exercised
elsewhere (test_pgvector_store.py); this file only proves the route no
longer blocks the event loop while that call is in flight.
"""
import asyncio
import time
from unittest.mock import MagicMock

import pytest

from src.api.v1.vectors import (
    VectorBatchRequest,
    VectorRecordAPI,
    VectorMetadataAPI,
    VectorSearchByDocRequest,
    VectorSearchRequest,
    add_vectors,
    delete_by_ingestion,
    search_by_document,
    similarity_search,
)

pytestmark = pytest.mark.unit

BLOCKING_SECONDS = 0.3
HEARTBEAT_INTERVAL = 0.02
# If the blocking call ran on the event loop instead of a worker thread,
# the heartbeat couldn't tick during it at all. A healthy loop should
# manage most of the ~15 available ticks; require a majority as a
# non-flaky floor.
MIN_EXPECTED_TICKS = 8


def _blocking_side_effect(*_args, **_kwargs):
    time.sleep(BLOCKING_SECONDS)
    return []


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


class TestVectorRoutesDoNotBlockEventLoop:
    def test_similarity_search_offloaded(self):
        store = MagicMock()
        store.similarity_search.side_effect = _blocking_side_effect
        request = VectorSearchRequest(query_vector=[0.1, 0.2, 0.3], k=3)

        ticks = asyncio.run(
            _run_concurrently(similarity_search(request, store=store))
        )

        assert len(ticks) >= MIN_EXPECTED_TICKS

    def test_delete_by_ingestion_offloaded(self):
        store = MagicMock()
        store.delete_by_ingestion_id.side_effect = _blocking_side_effect

        ticks = asyncio.run(
            _run_concurrently(delete_by_ingestion("ing-1", store=store))
        )

        assert len(ticks) >= MIN_EXPECTED_TICKS

    def test_add_vectors_offloaded(self):
        store = MagicMock()
        store.add.side_effect = _blocking_side_effect
        batch = VectorBatchRequest(
            records=[
                VectorRecordAPI(
                    vector=[0.1, 0.2],
                    metadata=VectorMetadataAPI(
                        ingestion_id="ing-1",
                        chunk_id="chunk-1",
                        chunk_index=0,
                        chunk_strategy="fixed",
                        chunk_text="hello",
                    ),
                )
            ]
        )

        ticks = asyncio.run(_run_concurrently(add_vectors(batch, store=store)))

        assert len(ticks) >= MIN_EXPECTED_TICKS


class TestVectorRoutesPreserveSemantics:
    """The offload must be transparent: same inputs, same outputs."""

    def test_similarity_search_still_returns_store_results(self):
        store = MagicMock()
        fake_result = MagicMock()
        fake_result.metadata.chunk_id = "c1"
        fake_result.metadata.chunk_text = "text"
        fake_result.metadata.document_id = "d1"
        fake_result.metadata.score = 0.9
        fake_result.metadata.ingestion_id = "ing-1"
        fake_result.metadata.chunk_index = 0
        fake_result.metadata.chunk_strategy = "fixed"
        fake_result.metadata.source_metadata = {}
        fake_result.metadata.provider = "mock"
        store.similarity_search.return_value = [fake_result]
        request = VectorSearchRequest(query_vector=[0.1, 0.2], k=1)

        result = asyncio.run(similarity_search(request, store=store))

        assert result["results"][0]["chunk_id"] == "c1"
        store.similarity_search.assert_called_once_with(
            [0.1, 0.2], 1, metadata_filter=None,
        )

    def test_search_by_document_still_returns_store_results(self):
        store = MagicMock()
        fake_result = MagicMock()
        fake_result.metadata.chunk_id = "c1"
        fake_result.metadata.chunk_text = "text"
        fake_result.metadata.document_id = "d1"
        fake_result.metadata.ingestion_id = "ing-1"
        fake_result.metadata.chunk_index = 0
        fake_result.metadata.chunk_strategy = "fixed"
        fake_result.metadata.source_metadata = {}
        fake_result.metadata.provider = "mock"
        store.get_chunks_by_document_id.return_value = [fake_result]
        request = VectorSearchByDocRequest(document_id="d1", k=3)

        result = asyncio.run(search_by_document(request, store=store))

        assert result["results"][0]["document_id"] == "d1"
        store.get_chunks_by_document_id.assert_called_once_with("d1", 3)
