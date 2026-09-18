# rag_orchestrator/tests/test_query_path_async_offload.py
"""
Issue #170 (WP-R7) PR 2: run_rag / run_simple_rag are `async def`, but
query embedding (OllamaEmbedder.embed -> synchronous requests.post),
optional reranking (CrossEncoder.predict -> synchronous CPU/GPU work),
and the codebase graph-cache fetch/check that hybrid_retrieve's graph
expansion depends on (get_cached_graph -> #168/WP-R5's synchronous
generation-check HTTP call, plus a synchronous full-graph HTTP fetch on a
cache miss) all previously ran directly on the event loop.

Each test here blocks one of those three seams with a plain time.sleep
stand-in for the real synchronous call, runs it concurrently with an
asyncio.sleep-based heartbeat, and asserts the heartbeat keeps ticking
throughout -- proof the blocking call is no longer running on the event
loop. This mirrors the PR 1 (delete_repo / vector-service routes)
concurrency tests. Correctness of embedding/reranking/graph-expansion
themselves is covered elsewhere (test_reranker.py, test_rerank_flag.py,
test_hybrid_retrieve_dedup.py); these tests only prove the offload.
"""
import asyncio
import time

import httpx
import pytest

import src.core.service as service
import src.core.simple_service as simple_service
from rag_orchestrator.src.retrieval import codebase_utils
from src.core.service import hybrid_retrieve

pytestmark = pytest.mark.unit

BLOCKING_SECONDS = 0.3
HEARTBEAT_INTERVAL = 0.02
# If the blocking call ran on the event loop instead of a worker thread,
# the heartbeat couldn't tick during it at all. A healthy loop should
# manage most of the ~15 available ticks; require a majority as a
# non-flaky floor.
MIN_EXPECTED_TICKS = 8


def _blocking_sleep(*_args, **_kwargs):
    time.sleep(BLOCKING_SECONDS)


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


def _patch_generate_call(monkeypatch):
    """Fake the final /generate call so run_rag/run_simple_rag can
    complete without a real llm_service."""

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"response": "ok", "model": "fake"})

    real_async_client = httpx.AsyncClient

    def patched_client(*args, **kwargs):
        kwargs["transport"] = httpx.MockTransport(handler)
        return real_async_client(*args, **kwargs)

    monkeypatch.setattr(httpx, "AsyncClient", patched_client)


def _patch_run_rag_pipeline(monkeypatch):
    """Fake every run_rag() dependency up to (not including) /generate,
    matching test_run_rag_model_override.py's pattern, so only the
    offloaded seam under test runs for real."""

    async def fake_resolve_repo_id_http(repo_id):
        return repo_id or "repo-x"

    monkeypatch.setattr(service, "resolve_repo_id_http", fake_resolve_repo_id_http)
    monkeypatch.setattr(service, "get_embedder", lambda **kwargs: object())

    async def fake_hybrid_retrieve(*args, **kwargs):
        return {}, {
            "seed_document_ids": [],
            "expanded_document_ids": [],
            "expansion_metadata": {},
        }

    monkeypatch.setattr(service, "hybrid_retrieve", fake_hybrid_retrieve)
    monkeypatch.setattr(service, "execute_retrieval_plan", lambda **kwargs: {})
    monkeypatch.setattr(service, "prepare_chunks_for_agent", lambda *a, **k: [])
    monkeypatch.setattr(
        service, "select_chunks_within_token_budget", lambda *a, **k: []
    )
    monkeypatch.setattr(service, "build_labeled_context", lambda *a, **k: ("", 0))
    monkeypatch.setattr(service, "build_final_context_manifest", lambda *a, **k: [])
    monkeypatch.setattr(service, "build_sources", lambda *a, **k: [])
    _patch_generate_call(monkeypatch)


class TestEmbedQueryOffloaded:
    def test_run_rag_embed_query_does_not_block_event_loop(self, monkeypatch):
        _patch_run_rag_pipeline(monkeypatch)
        monkeypatch.setattr(
            service,
            "embed_query",
            lambda query, embedder: (_blocking_sleep(), [0.0] * 8)[1],
        )

        ticks = asyncio.run(
            _run_concurrently(service.run_rag(query="what does main do?"))
        )

        assert len(ticks) >= MIN_EXPECTED_TICKS

    def test_run_simple_rag_embed_query_does_not_block_event_loop(
        self, monkeypatch
    ):
        monkeypatch.setattr(
            simple_service,
            "embed_query",
            lambda query, embedder: (_blocking_sleep(), [0.0] * 8)[1],
        )
        monkeypatch.setattr(simple_service, "get_embedder", lambda **kwargs: object())

        def search_handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(200, json={"results": []})

        real_async_client = httpx.AsyncClient

        def patched_client(*args, **kwargs):
            kwargs["transport"] = httpx.MockTransport(search_handler)
            return real_async_client(*args, **kwargs)

        monkeypatch.setattr(httpx, "AsyncClient", patched_client)

        ticks = asyncio.run(
            _run_concurrently(
                simple_service.run_simple_rag(query="what does the readme say?")
            )
        )

        assert len(ticks) >= MIN_EXPECTED_TICKS


class TestRerankOffloaded:
    def test_run_rag_rerank_does_not_block_event_loop(self, monkeypatch):
        _patch_run_rag_pipeline(monkeypatch)
        monkeypatch.setattr(service, "embed_query", lambda query, embedder: [0.0] * 8)
        monkeypatch.setattr(
            service, "rerank_chunks", lambda *a, **k: (_blocking_sleep(), [])[1]
        )

        ticks = asyncio.run(
            _run_concurrently(
                service.run_rag(query="what does main do?", rerank=True)
            )
        )

        assert len(ticks) >= MIN_EXPECTED_TICKS


class TestGraphCacheOffloaded:
    """Covers _rank_expanded_canonical_ids -> get_cached_graph (#168 /
    WP-R5's per-call generation check, and the full-graph fetch on a
    cache miss), exercised through hybrid_retrieve as in
    test_hybrid_retrieve_dedup.py."""

    def test_hybrid_retrieve_graph_cache_does_not_block_event_loop(
        self, monkeypatch
    ):
        def search_handler(request: httpx.Request) -> httpx.Response:
            if request.url.path == "/v1/vectors/search":
                return httpx.Response(
                    200,
                    json={
                        "results": [
                            {
                                "document_id": "doc-1",
                                "chunk_id": "chunk-1",
                                "text": "def run_demo(): pass",
                                "score": 0.9,
                                "metadata": {
                                    "relative_path": "kennel.py",
                                    "canonical_id": "kennel.py#run_demo",
                                },
                            }
                        ]
                    },
                )
            return httpx.Response(404)

        real_async_client = httpx.AsyncClient

        def patched_client(*args, **kwargs):
            kwargs["transport"] = httpx.MockTransport(search_handler)
            return real_async_client(*args, **kwargs)

        monkeypatch.setattr(httpx, "AsyncClient", patched_client)
        monkeypatch.setattr(
            codebase_utils,
            "get_cached_graph",
            lambda repo_id: (_blocking_sleep(), codebase_utils.CodebaseGraph())[1],
        )

        ticks = asyncio.run(
            _run_concurrently(
                hybrid_retrieve(
                    query="what does run_demo do",
                    repo_id="repo-x",
                    query_embedding=[0.0] * 8,
                    top_k=5,
                )
            )
        )

        assert len(ticks) >= MIN_EXPECTED_TICKS
