# rag_orchestrator/tests/test_wp_t1a_evidence_model.py
"""
WP-T1a (issue #100): extend the existing evidence-survival model rather
than build a parallel one --

  1. RetrievedChunk.canonical_id is a first-class field, not something
     every caller has to dig out of chunk.metadata by hand.
  2. RetrievalPlan.expansion_metadata (shared/retrieval/retrieval_plan.py)
     is actually populated for the codebase-graph retrieval path, with
     the relation type and originating seed document for every expanded
     document that survived the cap -- previously always {} because
     run_rag collapsed seed+expanded documents into one
     seed_document_ids set and never built the metadata at all.

Both are additive: no ranking, cap, fetch, or chunk-selection behavior
changes, which test_expansion_caps.py / test_evidence_survival.py /
test_multi_seed_traversal.py / test_inheritance_traversal.py already
cover and must keep passing unchanged.
"""
import asyncio
import json

import httpx
import pytest

from rag_orchestrator.src.retrieval import codebase_utils
from src.core.service import hybrid_retrieve, run_rag
from src.retrieval.codebase_queries import CodebaseGraph, Node
from src.retrieval.types import RetrievedChunk

pytestmark = pytest.mark.unit


def _build_graph() -> CodebaseGraph:
    """module.py DEFINES helper.py#helper and CALLs external.py#external --
    two different relation types reaching the seed's expansion, so
    expansion_metadata's relation_type field is actually exercised."""
    graph = CodebaseGraph()
    graph.add_node(Node("module.py", "module.py"))
    graph.add_node(Node("helper.py#helper", "helper.py"))
    graph.add_node(Node("external.py#external", "external.py"))
    graph.add_edge("module.py", "helper.py#helper", "DEFINES")
    graph.add_edge("module.py", "external.py#external", "CALL")
    return graph


class FakeBackend:
    def __init__(self):
        self.search_by_doc_docs = []

    def __call__(self, request: httpx.Request) -> httpx.Response:
        path = request.url.path

        if path == "/v1/vectors/search":
            return httpx.Response(
                200,
                json={
                    "results": [
                        {
                            "document_id": "module-doc",
                            "chunk_id": "module-chunk-0",
                            "text": "module docstring/header",
                            "score": 0.9,
                            "metadata": {
                                "canonical_id": "module.py",
                                "repo_id": "repo-x",
                            },
                        }
                    ]
                },
            )

        if path.startswith("/v1/graph/repos/"):
            nodes = [
                {"canonical_id": "module.py", "document_id": "module-doc"},
                {"canonical_id": "helper.py#helper", "document_id": "helper-doc"},
                {
                    "canonical_id": "external.py#external",
                    "document_id": "external-doc",
                },
            ]
            return httpx.Response(200, json={"nodes": nodes})

        if path == "/v1/vectors/search-by-doc":
            doc_id = json.loads(request.content)["document_id"]
            self.search_by_doc_docs.append(doc_id)
            return httpx.Response(
                200,
                json={
                    "results": [
                        {
                            "chunk_id": f"chunk-of-{doc_id}",
                            "text": f"implementation of {doc_id}",
                            "score": 0.5,
                            "metadata": {"canonical_id": f"{doc_id}-cid"},
                        }
                    ]
                },
            )

        if path == "/generate":
            return httpx.Response(200, json={"response": "ok"})

        return httpx.Response(404)


def _patched_client(backend):
    real_async_client = httpx.AsyncClient

    def patched(*args, **kwargs):
        kwargs["transport"] = httpx.MockTransport(backend)
        return real_async_client(*args, **kwargs)

    return patched


def _run_hybrid(monkeypatch, backend, query="explain the module"):
    monkeypatch.setattr(httpx, "AsyncClient", _patched_client(backend))
    monkeypatch.setattr(
        codebase_utils, "get_cached_graph", lambda repo_id: _build_graph()
    )
    return asyncio.run(
        hybrid_retrieve(
            query=query,
            repo_id="repo-x",
            query_embedding=[0.0] * 8,
            top_k=5,
        )
    )


# ------------------------------------------------------------------
# 1. RetrievedChunk.canonical_id is first-class
# ------------------------------------------------------------------


def test_retrieved_chunk_has_canonical_id_field():
    chunk = RetrievedChunk(
        chunk_id="c1",
        document_id="d1",
        text="text",
        score=1.0,
        metadata={"canonical_id": "a.py#f"},
        canonical_id="a.py#f",
    )
    assert chunk.canonical_id == "a.py#f"


def test_hybrid_retrieve_populates_canonical_id_on_seed_and_expanded_chunks(
    monkeypatch,
):
    backend = FakeBackend()
    chunks_by_doc, _ = _run_hybrid(monkeypatch, backend)

    seed_chunk = chunks_by_doc["module-doc"][0]
    assert seed_chunk.canonical_id == "module.py"

    expanded_chunk = chunks_by_doc["helper-doc"][0]
    assert expanded_chunk.canonical_id == "helper-doc-cid"


# ------------------------------------------------------------------
# 2. RetrievalPlan.expansion_metadata is populated (not always {})
# ------------------------------------------------------------------


def test_hybrid_retrieve_reports_expansion_metadata_with_relation_types(
    monkeypatch,
):
    backend = FakeBackend()
    _, plan = _run_hybrid(monkeypatch, backend)

    assert plan["seed_document_ids"] == ["module-doc"]
    assert set(plan["expanded_document_ids"]) == {"helper-doc", "external-doc"}

    metadata = plan["expansion_metadata"]
    assert metadata["helper-doc"] == {
        "source_document_id": "module-doc",
        "relation_type": "DEFINES",
    }
    assert metadata["external-doc"] == {
        "source_document_id": "module-doc",
        "relation_type": "CALL",
    }


def test_run_rag_builds_retrieval_plan_with_real_expansion_split(monkeypatch):
    """End-to-end (through run_rag, not just hybrid_retrieve): the
    RetrievalPlan actually constructed and executed carries the real
    seed/expanded split and non-empty expansion_metadata, closing the gap
    where it was always seed_document_ids=<everything>,
    expanded_document_ids=set(), expansion_metadata={}."""
    backend = FakeBackend()

    captured_plan = {}
    from rag_orchestrator.src.retrieval import execute_plan as execute_plan_module

    original_execute = execute_plan_module.execute_retrieval_plan

    def spying_execute(*, plan, **kwargs):
        captured_plan["plan"] = plan
        return original_execute(plan=plan, **kwargs)

    monkeypatch.setattr(
        "src.core.service.execute_retrieval_plan", spying_execute
    )

    async def fake_resolve_repo_id(repo_id):
        return repo_id or "repo-x"

    monkeypatch.setattr(httpx, "AsyncClient", _patched_client(backend))
    monkeypatch.setattr(
        codebase_utils, "get_cached_graph", lambda repo_id: _build_graph()
    )
    monkeypatch.setattr(
        "src.core.service.resolve_repo_id_http", fake_resolve_repo_id
    )
    monkeypatch.setattr(
        "src.core.service.embed_query", lambda query, embedder: [0.0] * 8
    )
    monkeypatch.setattr("src.core.service.get_embedder", lambda **kwargs: object())

    asyncio.run(run_rag(query="explain the module", repo_id="repo-x"))

    plan = captured_plan["plan"]
    assert plan.seed_document_ids == {"module-doc"}
    assert plan.expanded_document_ids == {"helper-doc", "external-doc"}
    assert plan.expansion_metadata["helper-doc"].relation_type == "DEFINES"
    assert plan.expansion_metadata["helper-doc"].source_document_id == "module-doc"
    assert plan.expansion_metadata["external-doc"].relation_type == "CALL"
