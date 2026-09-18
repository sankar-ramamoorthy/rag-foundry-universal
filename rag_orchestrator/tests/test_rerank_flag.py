# rag_orchestrator/tests/test_rerank_flag.py
"""
WP-S8: RERANK_ENABLED gating in run_rag() (graph-aware path) and
run_simple_rag() (flat document path) -- off by default, per-request
override in both directions, and both report whether reranking actually
ran. Isolates just the flag/wiring logic by faking out the retrieval
pipeline and rerank_chunks() itself (already covered in isolation by
test_reranker.py), same MockTransport pattern as
test_run_rag_model_override.py.
"""
import asyncio

import httpx
import pytest

import src.core.service as service
import src.core.simple_service as simple_service
from src.core.config import reset_settings_cache

pytestmark = pytest.mark.unit

_FAKE_CHUNKS = [{"chunk_id": "a", "text": "chunk a", "document_id": "doc-a"}]


def _mock_generate_transport():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"response": "ok", "model": "local"})

    return httpx.MockTransport(handler)


def _patch_run_rag_pipeline(monkeypatch, rerank_spy):
    async def fake_resolve_repo_id_http(repo_id):
        return repo_id or "repo-x"

    monkeypatch.setattr(service, "resolve_repo_id_http", fake_resolve_repo_id_http)
    monkeypatch.setattr(service, "get_embedder", lambda **kwargs: object())
    monkeypatch.setattr(service, "embed_query", lambda query, embedder: [0.0] * 8)

    async def fake_hybrid_retrieve(*args, **kwargs):
        return {}, {
            "seed_document_ids": [],
            "expanded_document_ids": [],
            "expansion_metadata": {},
        }

    monkeypatch.setattr(service, "hybrid_retrieve", fake_hybrid_retrieve)
    monkeypatch.setattr(service, "execute_retrieval_plan", lambda **kwargs: {})
    monkeypatch.setattr(
        service, "prepare_chunks_for_agent", lambda *a, **k: list(_FAKE_CHUNKS)
    )
    monkeypatch.setattr(service, "build_final_context_manifest", lambda *a, **k: [])
    monkeypatch.setattr(service, "build_sources", lambda *a, **k: [])
    monkeypatch.setattr(service, "rerank_chunks", rerank_spy)

    real_async_client = httpx.AsyncClient

    def patched_client(*args, **kwargs):
        kwargs["transport"] = _mock_generate_transport()
        return real_async_client(*args, **kwargs)

    monkeypatch.setattr(httpx, "AsyncClient", patched_client)


def _make_rerank_spy(calls):
    def spy(query, chunks, *, top_k, model_name):
        calls.append({"query": query, "chunks": chunks, "top_k": top_k})
        return chunks[:top_k]

    return spy


@pytest.fixture(autouse=True)
def _clean_settings():
    reset_settings_cache()
    yield
    reset_settings_cache()


def test_run_rag_rerank_off_by_default(monkeypatch):
    """RERANK_ENABLED defaults to False -- no rerank= override means the
    reranker never runs, and the result says so."""
    calls: list = []
    _patch_run_rag_pipeline(monkeypatch, _make_rerank_spy(calls))

    result = asyncio.run(service.run_rag(query="q", repo_id="repo-x"))

    assert calls == []
    assert result.reranked is False


def test_run_rag_rerank_explicit_true_overrides_default_off(monkeypatch):
    """Per-request rerank=True must run the reranker even though the
    deployment default is off -- the whole point of the override."""
    calls: list = []
    _patch_run_rag_pipeline(monkeypatch, _make_rerank_spy(calls))

    result = asyncio.run(
        service.run_rag(query="q", repo_id="repo-x", rerank=True)
    )

    assert len(calls) == 1
    assert calls[0]["chunks"] == _FAKE_CHUNKS
    assert result.reranked is True


def test_run_rag_rerank_explicit_false_overrides_enabled_default(monkeypatch):
    """The reverse override: even if RERANK_ENABLED were on, an explicit
    rerank=False for this request must skip it."""
    calls: list = []
    _patch_run_rag_pipeline(monkeypatch, _make_rerank_spy(calls))
    monkeypatch.setattr(service.get_settings(), "RERANK_ENABLED", True)

    result = asyncio.run(
        service.run_rag(query="q", repo_id="repo-x", rerank=False)
    )

    assert calls == []
    assert result.reranked is False


# ------------------------------------------------------------------
# run_simple_rag: same gating, non-graph path
# ------------------------------------------------------------------


def _patch_run_simple_rag_pipeline(monkeypatch, rerank_spy):
    monkeypatch.setattr(simple_service, "get_embedder", lambda **kwargs: object())
    monkeypatch.setattr(
        simple_service, "embed_query", lambda query, embedder: [0.0] * 8
    )
    monkeypatch.setattr(
        simple_service, "expand_retrieval_plan", lambda **kwargs: kwargs["plan"]
    )
    monkeypatch.setattr(simple_service, "execute_retrieval_plan", lambda **kwargs: {})
    monkeypatch.setattr(
        simple_service, "prepare_chunks_for_agent", lambda *a, **k: list(_FAKE_CHUNKS)
    )
    monkeypatch.setattr(simple_service, "build_sources", lambda *a, **k: [])
    monkeypatch.setattr(simple_service, "rerank_chunks", rerank_spy)

    real_async_client = httpx.AsyncClient

    def patched_client(*args, **kwargs):
        kwargs["transport"] = _mock_generate_transport()
        return real_async_client(*args, **kwargs)

    monkeypatch.setattr(httpx, "AsyncClient", patched_client)


def test_run_simple_rag_rerank_off_by_default(monkeypatch):
    calls: list = []
    _patch_run_simple_rag_pipeline(monkeypatch, _make_rerank_spy(calls))

    result = asyncio.run(simple_service.run_simple_rag(query="q"))

    assert calls == []
    assert result.reranked is False


def test_run_simple_rag_rerank_explicit_true_overrides_default_off(monkeypatch):
    calls: list = []
    _patch_run_simple_rag_pipeline(monkeypatch, _make_rerank_spy(calls))

    result = asyncio.run(simple_service.run_simple_rag(query="q", rerank=True))

    assert len(calls) == 1
    assert calls[0]["chunks"] == _FAKE_CHUNKS
    assert result.reranked is True
