# rag_orchestrator/tests/test_repo_scoping.py
"""
Issue #30 Part 1: the requested repo_id must survive the whole query path.

Covers the three defects that made every UI query silently answer from the
first completed repo:
- the /v1/rag route dropped repo_id before calling run_rag()
- the seed vector search had no repo_id metadata filter
- the no-code-chunks fallback popped the entire metadata_filter, which
  would reintroduce the cross-repo leak exactly when the requested repo
  has no matching code chunks
"""
import asyncio
import json

import httpx
import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient

import src.api.v1.routes as routes
from src.api.v1.main import app
from src.core.service import RAGResult, hybrid_retrieve

pytestmark = pytest.mark.unit


# ------------------------------------------------------------------
# Route: repo_id forwarding
# ------------------------------------------------------------------

def test_route_forwards_repo_id(monkeypatch):
    captured = {}

    async def fake_run_rag(**kwargs):
        captured.update(kwargs)
        return RAGResult(
            answer="ok", sources=[], repo_id=kwargs["repo_id"], retrieval_plan={}
        )

    monkeypatch.setattr(routes, "run_rag", fake_run_rag)

    client = TestClient(app)
    resp = client.post(
        "/v1/rag", json={"query": "what does main do?", "repo_id": "repo-x"}
    )

    assert resp.status_code == 200
    assert captured["repo_id"] == "repo-x"
    assert resp.json()["repo_id"] == "repo-x"


def test_route_forwards_none_when_repo_id_omitted(monkeypatch):
    captured = {}

    async def fake_run_rag(**kwargs):
        captured.update(kwargs)
        return RAGResult(
            answer="ok", sources=[], repo_id="first-complete", retrieval_plan={}
        )

    monkeypatch.setattr(routes, "run_rag", fake_run_rag)

    client = TestClient(app)
    resp = client.post("/v1/rag", json={"query": "hello"})

    assert resp.status_code == 200
    assert captured["repo_id"] is None


def test_route_propagates_unknown_repo_404(monkeypatch):
    async def fake_run_rag(**kwargs):
        raise HTTPException(404, "Repository not found")

    monkeypatch.setattr(routes, "run_rag", fake_run_rag)

    client = TestClient(app)
    resp = client.post("/v1/rag", json={"query": "q", "repo_id": "nope"})

    assert resp.status_code == 404


# ------------------------------------------------------------------
# hybrid_retrieve: seed filter and fallback stay repo-scoped
# ------------------------------------------------------------------

def _run_hybrid_with_empty_store(monkeypatch):
    """Run hybrid_retrieve against a vector store that returns no results,
    capturing every search payload it receives."""
    search_payloads = []

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/v1/vectors/search":
            search_payloads.append(json.loads(request.content))
        return httpx.Response(200, json={"results": []})

    real_async_client = httpx.AsyncClient

    def patched_client(*args, **kwargs):
        kwargs["transport"] = httpx.MockTransport(handler)
        return real_async_client(*args, **kwargs)

    monkeypatch.setattr(httpx, "AsyncClient", patched_client)

    asyncio.run(
        hybrid_retrieve(
            query="anything",
            repo_id="repo-x",
            query_embedding=[0.0] * 8,
            top_k=5,
        )
    )
    return search_payloads


def test_seed_search_is_repo_scoped(monkeypatch):
    payloads = _run_hybrid_with_empty_store(monkeypatch)

    assert payloads[0]["metadata_filter"] == {
        "source_type": "code",
        "repo_id": "repo-x",
    }


def test_fallback_relaxes_source_type_but_keeps_repo_scope(monkeypatch):
    payloads = _run_hybrid_with_empty_store(monkeypatch)

    # empty first response triggers the fallback retry
    assert len(payloads) == 2
    fallback_filter = payloads[1]["metadata_filter"]
    assert fallback_filter == {"repo_id": "repo-x"}
    assert "source_type" not in fallback_filter
