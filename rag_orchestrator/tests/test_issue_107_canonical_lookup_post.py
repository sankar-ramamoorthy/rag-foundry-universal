# rag_orchestrator/tests/test_issue_107_canonical_lookup_post.py
"""
Issue #107: canonical_to_document_map_http must send canonical_ids in a
POST JSON body to /v1/graph/repos/{repo_id}/nodes/lookup, not as a
comma-separated GET query string to /v1/graph/repos/{repo_id}/nodes.

Confirmed live: a 344-canonical_id GET request to the old endpoint
returned HTTP 400 "Invalid HTTP request received" once the query string
crossed ~19KB, and canonical_to_document_map_http's broad except-clause
silently turned that into an empty mapping -- identical, from every
caller's perspective, to "none of these canonical_ids matched anything."
That silently broke graph expansion (every expanded canonical_id fails
to resolve a document_id, so none get fetched) on any repo/query dense
enough to produce a few hundred combined seed+expansion canonical_ids.

This backend only implements POST .../nodes/lookup -- if
canonical_to_document_map_http ever regresses back to GET
.../nodes?canonical_ids=..., these tests fail loudly instead of the
regression silently reappearing as an empty mapping in production.
"""
import asyncio
import json

import httpx
import pytest

from src.core.service import canonical_to_document_map_http

pytestmark = pytest.mark.unit


class PostOnlyLookupBackend:
    """Mirrors the real ingestion_service graph API, but only serves the
    POST /lookup form -- any GET to the old query-string endpoint 400s,
    matching the real server's behavior once a batch is large enough,
    without needing an actual oversized request to prove the client
    uses the right endpoint/method."""

    def __init__(self, nodes_by_cid):
        self.nodes_by_cid = nodes_by_cid
        self.requests = []

    def __call__(self, request: httpx.Request) -> httpx.Response:
        self.requests.append(request)
        if request.method == "POST" and request.url.path.endswith("/nodes/lookup"):
            payload = json.loads(request.content)
            cids = payload["canonical_ids"]
            nodes = [self.nodes_by_cid[c] for c in cids if c in self.nodes_by_cid]
            return httpx.Response(200, json={"nodes": nodes, "total": len(nodes)})
        if request.method == "GET" and request.url.path.endswith("/nodes"):
            return httpx.Response(400, text="Invalid HTTP request received.")
        return httpx.Response(404)


def _patched_client(backend):
    real_async_client = httpx.AsyncClient

    def patched(*args, **kwargs):
        kwargs["transport"] = httpx.MockTransport(backend)
        return real_async_client(*args, **kwargs)

    return patched


def test_uses_post_lookup_not_get_query_string(monkeypatch):
    backend = PostOnlyLookupBackend({})
    monkeypatch.setattr(httpx, "AsyncClient", _patched_client(backend))

    asyncio.run(canonical_to_document_map_http("repo-x", {"a.py#f"}))

    assert len(backend.requests) == 1
    req = backend.requests[0]
    assert req.method == "POST"
    assert req.url.path.endswith("/nodes/lookup")


def test_resolves_a_large_batch_that_would_overflow_a_get_query_string(monkeypatch):
    n = 400
    nodes_by_cid = {
        f"pkg/module_{i}.py#func_{i}": {
            "document_id": f"doc-{i}",
            "canonical_id": f"pkg/module_{i}.py#func_{i}",
            "relative_path": f"pkg/module_{i}.py",
            "title": f"func_{i}",
            "doc_type": "python source",
        }
        for i in range(n)
    }
    backend = PostOnlyLookupBackend(nodes_by_cid)
    monkeypatch.setattr(httpx, "AsyncClient", _patched_client(backend))

    mapping = asyncio.run(
        canonical_to_document_map_http("repo-x", set(nodes_by_cid.keys()))
    )

    assert len(mapping) == n
    assert all(mapping[cid] == nodes_by_cid[cid]["document_id"] for cid in mapping)


def test_http_error_response_returns_empty_mapping_without_raising(monkeypatch):
    def backend(request: httpx.Request) -> httpx.Response:
        return httpx.Response(500, text="boom")

    monkeypatch.setattr(httpx, "AsyncClient", _patched_client(backend))

    mapping = asyncio.run(canonical_to_document_map_http("repo-x", {"a.py#f"}))
    assert mapping == {}


def test_no_canonical_ids_makes_no_request(monkeypatch):
    calls = []

    def backend(request: httpx.Request) -> httpx.Response:
        calls.append(request)
        return httpx.Response(200, json={"nodes": []})

    monkeypatch.setattr(httpx, "AsyncClient", _patched_client(backend))

    mapping = asyncio.run(canonical_to_document_map_http("repo-x", set()))
    assert mapping == {}
    assert calls == []
