# rag_orchestrator/tests/test_explicit_mention_context_priority.py
"""
Issue #254 (context-allocation follow-up to #257): a document reached
only via an explicit `ClassName.method_name` mention was still placed
behind every seed document in `document_order` (issue #30 Part 3's
deliberate seed-first default), regardless of that explicit relevance
signal -- confirmed live to starve `agent.py#Agent.run`'s chunks out of
the context budget entirely even after #257 made discovery/fetch work.

`_prioritize_explicit_mentions` moves just that narrow, already-bounded
set of documents ahead of ordinary seeds. It must never reorder anything
else, and must be a true no-op (same list, same identity) when nothing
was explicitly mentioned.
"""
import asyncio
import json

import httpx
import pytest

from rag_orchestrator.src.retrieval import codebase_utils
from src.core.service import _prioritize_explicit_mentions, hybrid_retrieve, run_rag
from src.retrieval.codebase_queries import CodebaseGraph, Node

pytestmark = pytest.mark.unit


# ------------------------------------------------------------------
# 1. Pure function
# ------------------------------------------------------------------


def test_noop_when_nothing_explicitly_mentioned():
    doc_ids = ["seed-1", "seed-2", "expanded-1"]
    result = _prioritize_explicit_mentions(doc_ids, [])
    assert result is doc_ids  # identity, not just equality


def test_promotes_only_the_named_documents():
    doc_ids = ["seed-1", "seed-2", "expanded-1", "expanded-2", "expanded-3"]
    result = _prioritize_explicit_mentions(doc_ids, ["expanded-2"])
    assert result == ["expanded-2", "seed-1", "seed-2", "expanded-1", "expanded-3"]


def test_relative_order_preserved_within_each_group():
    doc_ids = ["seed-1", "seed-2", "expanded-1", "expanded-2"]
    result = _prioritize_explicit_mentions(doc_ids, ["expanded-2", "expanded-1"])
    # promoted group keeps doc_ids' own relative order, not the caller's
    assert result == ["expanded-1", "expanded-2", "seed-1", "seed-2"]


def test_does_not_add_or_remove_documents():
    doc_ids = ["a", "b", "c"]
    result = _prioritize_explicit_mentions(doc_ids, ["z"])  # not present at all
    assert sorted(result) == sorted(doc_ids)
    assert set(result) == set(doc_ids)


# ------------------------------------------------------------------
# 2. hybrid_retrieve populates explicit_mention_document_ids
# ------------------------------------------------------------------


def _build_graph() -> CodebaseGraph:
    """module.py (seed) --CALL--> agent.py#Agent --DEFINES--> Agent.run.
    Mirrors #254's real shape: Agent reaches the candidate set via CALL
    from a different seed, not via DEFINES from being a seed itself."""
    graph = CodebaseGraph()
    graph.add_node(Node("module.py", "module.py"))
    graph.add_node(Node("agent.py#Agent", "agent.py"))
    graph.add_node(Node("agent.py#Agent.run", "agent.py"))
    graph.add_edge("module.py", "agent.py#Agent", "CALL")
    graph.add_edge("agent.py#Agent", "agent.py#Agent.run", "DEFINES")
    return graph


class FakeBackend:
    def __call__(self, request: httpx.Request) -> httpx.Response:
        path = request.url.path
        if path.endswith("/generation"):
            return httpx.Response(200, json={
                "ingestion_id": "generation-1", "generation_status": "ready",
            })

        if path == "/v1/vectors/search":
            return httpx.Response(200, json={"results": [
                {
                    "document_id": "module-doc",
                    "chunk_id": "module-chunk-0",
                    "text": "module docstring",
                    "score": 0.9,
                    "metadata": {"canonical_id": "module.py", "repo_id": "repo-x"},
                },
            ]})

        if path.startswith("/v1/graph/repos/"):
            nodes = [
                {"canonical_id": "module.py", "document_id": "module-doc"},
                {"canonical_id": "agent.py#Agent", "document_id": "agent-doc"},
                {
                    "canonical_id": "agent.py#Agent.run",
                    "document_id": "agent-run-doc",
                },
            ]
            return httpx.Response(200, json={"nodes": nodes})

        if path == "/v1/vectors/search-by-doc":
            doc_id = json.loads(request.content)["document_id"]
            return httpx.Response(200, json={"results": [
                {
                    "chunk_id": f"chunk-of-{doc_id}",
                    "text": f"implementation of {doc_id}",
                    "score": 0.5,
                    "metadata": {"canonical_id": f"{doc_id}-cid"},
                },
            ]})

        if path == "/generate":
            return httpx.Response(200, json={"response": "ok"})

        return httpx.Response(404)


def _patched_client(backend):
    real_async_client = httpx.AsyncClient

    def patched(*args, **kwargs):
        kwargs["transport"] = httpx.MockTransport(backend)
        return real_async_client(*args, **kwargs)

    return patched


def test_hybrid_retrieve_reports_explicit_mention_document_ids(monkeypatch):
    backend = FakeBackend()
    monkeypatch.setattr(httpx, "AsyncClient", _patched_client(backend))
    monkeypatch.setattr(
        codebase_utils, "get_cached_graph", lambda repo_id: _build_graph()
    )

    _, plan = asyncio.run(hybrid_retrieve(
        query="trace `Agent.run` to the next LLM call",
        repo_id="repo-x",
        query_embedding=[0.0] * 8,
        top_k=5,
    ))

    assert plan["explicit_mention_document_ids"] == ["agent-run-doc"]
    assert "agent-run-doc" in plan["expanded_document_ids"]


def test_hybrid_retrieve_reports_no_explicit_mentions_when_query_has_none(
    monkeypatch,
):
    backend = FakeBackend()
    monkeypatch.setattr(httpx, "AsyncClient", _patched_client(backend))
    monkeypatch.setattr(
        codebase_utils, "get_cached_graph", lambda repo_id: _build_graph()
    )

    _, plan = asyncio.run(hybrid_retrieve(
        query="what does the module do?",
        repo_id="repo-x",
        query_embedding=[0.0] * 8,
        top_k=5,
    ))

    assert plan["explicit_mention_document_ids"] == []


# ------------------------------------------------------------------
# 3. run_rag actually reorders document_order ahead of seeds
# ------------------------------------------------------------------


def test_run_rag_promotes_explicitly_mentioned_document_ahead_of_seeds(
    monkeypatch,
):
    backend = FakeBackend()
    captured = {}

    import rag_orchestrator.src.core.service as service_module
    original_prepare = service_module.prepare_chunks_for_agent

    def spying_prepare(*args, **kwargs):
        captured["document_order"] = kwargs.get("document_order")
        return original_prepare(*args, **kwargs)

    monkeypatch.setattr(
        "src.core.service.prepare_chunks_for_agent", spying_prepare
    )

    async def fake_resolve_repo_id(repo_id):
        return repo_id or "repo-x"

    monkeypatch.setattr(httpx, "AsyncClient", _patched_client(backend))
    monkeypatch.setattr(
        codebase_utils, "get_cached_graph", lambda repo_id: _build_graph()
    )
    monkeypatch.setattr("src.core.service.resolve_repo_id_http", fake_resolve_repo_id)
    monkeypatch.setattr(
        "src.core.service.embed_query", lambda query, embedder: [0.0] * 8
    )
    monkeypatch.setattr("src.core.service.get_embedder", lambda **kwargs: object())

    asyncio.run(run_rag(
        query="trace `Agent.run` to the next LLM call", repo_id="repo-x",
    ))

    order = captured["document_order"]
    assert order[0] == "agent-run-doc"
    assert order.index("agent-run-doc") < order.index("module-doc")


def test_run_rag_document_order_unchanged_without_explicit_mention(monkeypatch):
    """Negative control: no explicit mention -> identical seed-first order
    as before this change (module-doc, then expansion in rank order)."""
    backend = FakeBackend()
    captured = {}

    import rag_orchestrator.src.core.service as service_module
    original_prepare = service_module.prepare_chunks_for_agent

    def spying_prepare(*args, **kwargs):
        captured["document_order"] = kwargs.get("document_order")
        return original_prepare(*args, **kwargs)

    monkeypatch.setattr(
        "src.core.service.prepare_chunks_for_agent", spying_prepare
    )

    async def fake_resolve_repo_id(repo_id):
        return repo_id or "repo-x"

    monkeypatch.setattr(httpx, "AsyncClient", _patched_client(backend))
    monkeypatch.setattr(
        codebase_utils, "get_cached_graph", lambda repo_id: _build_graph()
    )
    monkeypatch.setattr("src.core.service.resolve_repo_id_http", fake_resolve_repo_id)
    monkeypatch.setattr(
        "src.core.service.embed_query", lambda query, embedder: [0.0] * 8
    )
    monkeypatch.setattr("src.core.service.get_embedder", lambda **kwargs: object())

    asyncio.run(run_rag(query="what does the module do?", repo_id="repo-x"))

    order = captured["document_order"]
    assert order[0] == "module-doc"
