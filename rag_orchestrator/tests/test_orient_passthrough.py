# rag_orchestrator/tests/test_orient_passthrough.py
"""
Issue #216: rag_orchestrator exposes ingestion_service's deterministic
ORIENT endpoint (issue #197) as a thin passthrough -- no vector search,
no graph expansion, no LLM call. Unlike /models, ingestion_service's own
404/409 must survive the hop, not collapse into a generic status.
"""

import httpx
import pytest
from fastapi.testclient import TestClient

from src.api.v1.main import app

pytestmark = pytest.mark.unit


def _patched_client(monkeypatch, handler):
    real_async_client = httpx.AsyncClient

    def patched(*args, **kwargs):
        kwargs["transport"] = httpx.MockTransport(handler)
        return real_async_client(*args, **kwargs)

    monkeypatch.setattr(httpx, "AsyncClient", patched)


def test_orient_passthrough_success(monkeypatch):
    orient_body = {
        "repo_id": "repo-x",
        "ingestion_id": "ing-1",
        "generation_status": "ready",
        "commit_sha": "abc123",
        "languages": {"python": 3},
        "file_counts": {"indexed": 3, "non_indexed": 0, "total": 3},
        "manifests": [],
        "services": [],
        "test_dirs": [],
        "docs_dirs": [],
        "heuristic_fields": ["test_dirs", "docs_dirs"],
        "gaps": [],
        "computed_at": None,
    }

    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/v1/repos/repo-x/orient"
        return httpx.Response(200, json=orient_body)

    _patched_client(monkeypatch, handler)
    client = TestClient(app)
    response = client.get("/v1/repos/repo-x/orient")

    assert response.status_code == 200
    assert response.json() == orient_body


def test_orient_passthrough_404_survives_the_hop(monkeypatch):
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            404, json={"detail": "No completed generation for repo_id=repo-x"}
        )

    _patched_client(monkeypatch, handler)
    client = TestClient(app)
    response = client.get("/v1/repos/repo-x/orient")

    assert response.status_code == 404
    assert "No completed generation" in response.json()["detail"]


def test_orient_passthrough_409_survives_the_hop(monkeypatch):
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            409,
            json={
                "detail": "This generation predates ORIENT -- re-ingest to populate."
            },
        )

    _patched_client(monkeypatch, handler)
    client = TestClient(app)
    response = client.get("/v1/repos/repo-x/orient")

    assert response.status_code == 409
    assert "predates ORIENT" in response.json()["detail"]


def test_orient_passthrough_502_when_ingestion_service_down(monkeypatch):
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("down")

    _patched_client(monkeypatch, handler)
    client = TestClient(app)

    assert client.get("/v1/repos/repo-x/orient").status_code == 502


def test_orient_passthrough_502_on_unexpected_status(monkeypatch):
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(500, text="internal error")

    _patched_client(monkeypatch, handler)
    client = TestClient(app)

    assert client.get("/v1/repos/repo-x/orient").status_code == 502
