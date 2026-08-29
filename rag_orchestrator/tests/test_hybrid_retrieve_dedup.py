# rag_orchestrator/tests/test_hybrid_retrieve_dedup.py
"""
Issue #65: hybrid_retrieve() must drop near-duplicate seed chunks (a
module/root artifact whose sole child covers ~the same text) before they
reach the final candidate set — this is the wiring test for
dedupe_near_identical_chunks(), proving it actually runs inside
hybrid_retrieve() and that the dropped chunk disappears from both the
returned chunks and the retrieval plan's seed_canonical_ids.
"""
import asyncio

import httpx
import pytest

from rag_orchestrator.src.retrieval import codebase_utils
from src.core.service import hybrid_retrieve
from src.retrieval.codebase_queries import CodebaseGraph, Node

pytestmark = pytest.mark.unit

README_TEXT = (
    "# smoke_repo\n\nThis fixture backs the live smoke test. "
    "It ingests a tiny repo and asks a handful of questions."
)


def _build_graph() -> CodebaseGraph:
    graph = CodebaseGraph()
    graph.add_node(Node("README.md", "README.md"))
    graph.add_node(Node("README.md#smoke_repo", "README.md"))
    graph.add_node(Node("kennel.py", "kennel.py"))
    return graph


def _search_response(request: httpx.Request) -> httpx.Response:
    if request.url.path == "/v1/vectors/search":
        return httpx.Response(
            200,
            json={
                "results": [
                    {
                        "document_id": "doc-module",
                        "chunk_id": "chunk-module",
                        "text": README_TEXT,
                        "score": 0.81,
                        "metadata": {
                            "relative_path": "README.md",
                            "canonical_id": "README.md",
                        },
                    },
                    {
                        "document_id": "doc-section",
                        "chunk_id": "chunk-section",
                        "text": README_TEXT,
                        "score": 0.79,
                        "metadata": {
                            "relative_path": "README.md",
                            "canonical_id": "README.md#smoke_repo",
                        },
                    },
                    {
                        "document_id": "doc-distinct",
                        "chunk_id": "chunk-distinct",
                        "text": "def run_demo():\n    return train_dog()",
                        "score": 0.5,
                        "metadata": {
                            "relative_path": "kennel.py",
                            "canonical_id": "kennel.py#run_demo",
                        },
                    },
                ]
            },
        )
    if request.url.path.startswith("/v1/graph/repos/"):
        return httpx.Response(200, json={"nodes": []})
    return httpx.Response(404)


def test_hybrid_retrieve_drops_near_duplicate_seed_chunk(monkeypatch):
    real_async_client = httpx.AsyncClient

    def patched_client(*args, **kwargs):
        kwargs["transport"] = httpx.MockTransport(_search_response)
        return real_async_client(*args, **kwargs)

    monkeypatch.setattr(httpx, "AsyncClient", patched_client)
    monkeypatch.setattr(
        codebase_utils, "get_cached_graph", lambda repo_id: _build_graph()
    )

    chunks_by_doc, plan = asyncio.run(
        hybrid_retrieve(
            query="what does the readme say",
            repo_id="repo-x",
            query_embedding=[0.0] * 8,
            top_k=5,
        )
    )

    all_chunk_ids = {
        c.chunk_id for chunks in chunks_by_doc.values() for c in chunks
    }
    # The lower-scoring duplicate (section) is gone; the module and the
    # unrelated distinct chunk both survive.
    assert all_chunk_ids == {"chunk-module", "chunk-distinct"}
    assert "chunk-section" not in all_chunk_ids

    assert "README.md#smoke_repo" not in plan["seed_canonical_ids"]
    assert "README.md" in plan["seed_canonical_ids"]
    assert plan["seed_docs"] == 2
