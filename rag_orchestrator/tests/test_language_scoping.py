# rag_orchestrator/tests/test_language_scoping.py
"""
WP-L6a (#85, specs/003-language-aware-retrieval): an optional `language`
scope on /v1/rag must reach the seed vector search's metadata_filter, must
survive the existing source_type-relaxation fallback the same way repo_id
already does (issue #30 Part 1), and must leave today's unfiltered
behavior byte-identical when omitted.

Mirrors rag_orchestrator/tests/test_repo_scoping.py's exact structure and
test-harness style.
"""
import asyncio
import json

import httpx
import pytest
from fastapi.testclient import TestClient

import src.api.v1.routes as routes
from src.api.v1.main import app
from src.core.service import RAGResult, hybrid_retrieve

pytestmark = pytest.mark.unit


# ------------------------------------------------------------------
# Route: language forwarding
# ------------------------------------------------------------------

def test_route_forwards_language(monkeypatch):
    captured = {}

    async def fake_run_rag(**kwargs):
        captured.update(kwargs)
        return RAGResult(
            answer="ok", sources=[], repo_id=kwargs["repo_id"], retrieval_plan={}
        )

    monkeypatch.setattr(routes, "run_rag", fake_run_rag)

    client = TestClient(app)
    resp = client.post(
        "/v1/rag",
        json={"query": "what does main do?", "repo_id": "repo-x", "language": "python"},
    )

    assert resp.status_code == 200
    assert captured["language"] == "python"


def test_route_forwards_none_when_language_omitted(monkeypatch):
    captured = {}

    async def fake_run_rag(**kwargs):
        captured.update(kwargs)
        return RAGResult(
            answer="ok", sources=[], repo_id="repo-x", retrieval_plan={}
        )

    monkeypatch.setattr(routes, "run_rag", fake_run_rag)

    client = TestClient(app)
    resp = client.post("/v1/rag", json={"query": "hello", "repo_id": "repo-x"})

    assert resp.status_code == 200
    assert captured["language"] is None


# ------------------------------------------------------------------
# hybrid_retrieve: seed filter and fallback carry the language scope
# ------------------------------------------------------------------

def _run_hybrid_with_empty_store(monkeypatch, language=None):
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
            language=language,
        )
    )
    return search_payloads


@pytest.mark.parametrize("language", ["python", "typescript", "javascript"])
def test_seed_search_is_language_scoped(monkeypatch, language):
    payloads = _run_hybrid_with_empty_store(monkeypatch, language=language)

    assert payloads[0]["metadata_filter"] == {
        "source_type": "code",
        "repo_id": "repo-x",
        "language": language,
    }


def test_seed_search_has_no_language_key_when_omitted(monkeypatch):
    """No-regression check (FR-006/SC-002): omitting language must leave
    the filter dict exactly as it was before this feature existed — no
    `language: None` key, not just a falsy one."""
    payloads = _run_hybrid_with_empty_store(monkeypatch, language=None)

    assert payloads[0]["metadata_filter"] == {
        "source_type": "code",
        "repo_id": "repo-x",
    }
    assert "language" not in payloads[0]["metadata_filter"]


def test_fallback_keeps_language_scope(monkeypatch):
    payloads = _run_hybrid_with_empty_store(monkeypatch, language="python")

    # empty first response triggers the fallback retry
    assert len(payloads) == 2
    fallback_filter = payloads[1]["metadata_filter"]
    assert fallback_filter == {"repo_id": "repo-x", "language": "python"}
    assert "source_type" not in fallback_filter


def test_fallback_has_no_language_key_when_omitted(monkeypatch):
    """Regression check mirroring test_repo_scoping.py's
    test_fallback_relaxes_source_type_but_keeps_repo_scope."""
    payloads = _run_hybrid_with_empty_store(monkeypatch, language=None)

    assert len(payloads) == 2
    fallback_filter = payloads[1]["metadata_filter"]
    assert fallback_filter == {"repo_id": "repo-x"}
    assert "language" not in fallback_filter
