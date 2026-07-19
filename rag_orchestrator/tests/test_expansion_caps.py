# rag_orchestrator/tests/test_expansion_caps.py
"""
Issue #30 Part 3: graph expansion is bounded, deduplicated, and observable.

Before: every expanded document triggered a sequential search-by-doc HTTP
call with k=10 and no cap on expanded docs, agent chunks were uncapped
(max_total_chunks=9999), and nothing deduplicated chunk_ids across the
seed/expanded merge.
"""
import asyncio
import json
from dataclasses import dataclass

import httpx
import pytest

from rag_orchestrator.src.retrieval import codebase_utils
from src.core.config import get_settings
from src.core.service import hybrid_retrieve
from src.retrieval.codebase_queries import CodebaseGraph, Node
from src.retrieval.traversal_selector import execute_traversals_from_seeds

pytestmark = pytest.mark.unit

N_EXPANDED = 30  # more than MAX_EXPANDED_DOCS (default 20)


def _build_graph() -> CodebaseGraph:
    graph = CodebaseGraph()
    graph.add_node(Node("a.py", "a.py"))
    for i in range(N_EXPANDED):
        cid = f"n{i:02d}"
        graph.add_node(Node(cid, f"{cid}.py"))
        graph.add_edge("a.py", cid, "DEFINES")
    return graph


class FakeBackend:
    """Handles vector-store and graph-API requests, counting calls."""

    def __init__(self):
        self.search_calls = 0
        self.search_by_doc_calls = 0
        self.search_by_doc_docs = []

    def __call__(self, request: httpx.Request) -> httpx.Response:
        path = request.url.path
        if path == "/v1/vectors/search":
            self.search_calls += 1
            results = [
                {
                    "document_id": "seed-doc",
                    "chunk_id": "seed-chunk-1",
                    "text": "seed text",
                    "score": 0.9,
                    "metadata": {"canonical_id": "a.py", "repo_id": "repo-x"},
                },
                # duplicate chunk_id straight from the store — must collapse
                {
                    "document_id": "seed-doc",
                    "chunk_id": "seed-chunk-1",
                    "text": "seed text",
                    "score": 0.9,
                    "metadata": {"canonical_id": "a.py", "repo_id": "repo-x"},
                },
            ]
            return httpx.Response(200, json={"results": results})

        if path.startswith("/v1/graph/repos/"):
            nodes = [{"canonical_id": "a.py", "document_id": "seed-doc"}]
            nodes += [
                {"canonical_id": f"n{i:02d}", "document_id": f"doc-{i:02d}"}
                for i in range(N_EXPANDED)
            ]
            return httpx.Response(200, json={"nodes": nodes})

        if path == "/v1/vectors/search-by-doc":
            self.search_by_doc_calls += 1
            doc_id = json.loads(request.content)["document_id"]
            self.search_by_doc_docs.append(doc_id)
            results = [
                {
                    "chunk_id": f"chunk-of-{doc_id}",
                    "text": "expanded text",
                    "score": 0.5,
                    "metadata": {},
                },
                # same chunk_id returned by every doc — dedup must keep one
                {
                    "chunk_id": "dup-chunk",
                    "text": "duplicated",
                    "score": 0.4,
                    "metadata": {},
                },
            ]
            return httpx.Response(200, json={"results": results})

        return httpx.Response(404)


def _run_hybrid(monkeypatch, backend):
    real_async_client = httpx.AsyncClient

    def patched_client(*args, **kwargs):
        kwargs["transport"] = httpx.MockTransport(backend)
        return real_async_client(*args, **kwargs)

    monkeypatch.setattr(httpx, "AsyncClient", patched_client)
    monkeypatch.setattr(
        codebase_utils, "get_cached_graph", lambda repo_id: _build_graph()
    )

    return asyncio.run(
        hybrid_retrieve(
            query="explain the module",  # default routing → defines + calls
            repo_id="repo-x",
            query_embedding=[0.0] * 8,
            top_k=5,
        )
    )


def test_expansion_fetches_are_capped(monkeypatch):
    backend = FakeBackend()
    chunks_by_doc, plan = _run_hybrid(monkeypatch, backend)

    cap = get_settings().MAX_EXPANDED_DOCS
    assert backend.search_by_doc_calls == cap
    # bounded number of vector-store calls: 1 seed search + capped fetches
    assert backend.search_calls + backend.search_by_doc_calls == cap + 1

    assert plan["expanded_docs_considered"] == N_EXPANDED
    assert plan["expanded_docs_used"] == cap


def test_no_duplicate_chunk_ids_across_seed_and_expansion(monkeypatch):
    backend = FakeBackend()
    chunks_by_doc, _ = _run_hybrid(monkeypatch, backend)

    all_chunk_ids = [
        c.chunk_id for chunks in chunks_by_doc.values() for c in chunks
    ]
    assert len(all_chunk_ids) == len(set(all_chunk_ids))
    assert all_chunk_ids.count("dup-chunk") == 1
    assert all_chunk_ids.count("seed-chunk-1") == 1


def test_expanded_fetch_uses_configured_chunk_count(monkeypatch):
    backend = FakeBackend()
    captured_k = []

    original_call = backend.__call__

    def spying(request):
        if request.url.path == "/v1/vectors/search-by-doc":
            captured_k.append(json.loads(request.content)["k"])
        return original_call(request)

    _run_hybrid(monkeypatch, spying)

    settings = get_settings()
    assert captured_k and all(k == settings.EXPANDED_DOC_CHUNKS for k in captured_k)


# ------------------------------------------------------------------
# Ranking: nodes reached from more seeds come first
# ------------------------------------------------------------------

@dataclass(frozen=True)
class FakeNode:
    canonical_id: str


def test_expansion_ranks_by_seed_adjacency():
    def strategy(graph, start_cid):
        if start_cid == "seed1":
            return [FakeNode("solo"), FakeNode("shared")]
        return [FakeNode("shared")]

    nodes = execute_traversals_from_seeds(
        graph=None,
        seed_canonical_ids={"seed1", "seed2"},
        strategies=[strategy],
    )
    assert [n.canonical_id for n in nodes] == ["shared", "solo"]


def test_ranking_ties_break_deterministically():
    def strategy(graph, start_cid):
        return [FakeNode("b"), FakeNode("a")]

    nodes = execute_traversals_from_seeds(
        graph=None,
        seed_canonical_ids={"seed1"},
        strategies=[strategy],
    )
    assert [n.canonical_id for n in nodes] == ["a", "b"]
