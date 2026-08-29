# rag_orchestrator/tests/test_source_type_separation.py
"""
Issue #64: source_type is the single shared marker that separates the two
RAG paths — code RAG must select it, document RAG must exclude it. This
locks in that separation as an explicit regression rather than leaving it
to be inferred from the two call sites.

hybrid_retrieve() (code path) is covered by test_repo_scoping.py; this
file covers run_simple_rag()'s (document path) search payload without
exercising the rest of its pipeline (retrieval-plan expansion, LLM call),
by making the mocked vector-store response an error so run_simple_rag()
exits via its existing "vector search failed" HTTPException right after
capturing the payload.
"""
import asyncio
import json

import httpx
import pytest
from fastapi import HTTPException

from src.core import simple_service
from src.core.simple_service import run_simple_rag

pytestmark = pytest.mark.unit


def test_simple_rag_search_excludes_code(monkeypatch):
    monkeypatch.setattr(
        simple_service, "embed_query", lambda query, embedder: [0.0] * 8
    )

    captured = {}

    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/v1/vectors/search"
        captured["payload"] = json.loads(request.content)
        return httpx.Response(500, json={"detail": "boom"})

    real_async_client = httpx.AsyncClient

    def patched_client(*args, **kwargs):
        kwargs["transport"] = httpx.MockTransport(handler)
        return real_async_client(*args, **kwargs)

    monkeypatch.setattr(httpx, "AsyncClient", patched_client)

    with pytest.raises(HTTPException):
        asyncio.run(run_simple_rag(query="anything"))

    assert captured["payload"]["metadata_filter"] == {"source_type": {"ne": "code"}}
