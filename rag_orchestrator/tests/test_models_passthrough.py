# rag_orchestrator/tests/test_models_passthrough.py
"""
WP-M5: the orchestrator exposes llm_service's model menu and surfaces
the model actually used in RAG responses.
"""
import httpx
import pytest
from fastapi.testclient import TestClient

import src.api.v1.routes as routes
from src.api.v1.main import app
from src.core.service import RAGResult

pytestmark = pytest.mark.unit


def test_models_passthrough(monkeypatch):
    menu = {
        "models": [
            {"alias": "default", "model": "ollama/phi4-mini:latest",
             "is_default": True},
            {"alias": "smart", "model": "anthropic/claude-sonnet-5",
             "is_default": False},
        ],
        "default": "default",
    }

    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/v1/models"
        return httpx.Response(200, json=menu)

    real_async_client = httpx.AsyncClient

    def patched_client(*args, **kwargs):
        kwargs["transport"] = httpx.MockTransport(handler)
        return real_async_client(*args, **kwargs)

    monkeypatch.setattr(httpx, "AsyncClient", patched_client)

    client = TestClient(app)
    response = client.get("/v1/models")

    assert response.status_code == 200
    assert response.json() == menu


def test_models_passthrough_502_when_llm_service_down(monkeypatch):
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("down")

    real_async_client = httpx.AsyncClient

    def patched_client(*args, **kwargs):
        kwargs["transport"] = httpx.MockTransport(handler)
        return real_async_client(*args, **kwargs)

    monkeypatch.setattr(httpx, "AsyncClient", patched_client)

    client = TestClient(app)
    assert client.get("/v1/models").status_code == 502


def test_rag_response_carries_model_metadata(monkeypatch):
    async def fake_run_rag(**kwargs):
        return RAGResult(
            answer="ok",
            sources=[],
            repo_id="repo-x",
            retrieval_plan={},
            model_used="openai/gpt-5.1",
            model_alias="smart",
            fallback_from="anthropic/claude-sonnet-5",
        )

    monkeypatch.setattr(routes, "run_rag", fake_run_rag)

    client = TestClient(app)
    response = client.post("/v1/rag", json={"query": "q", "repo_id": "repo-x"})

    assert response.status_code == 200
    body = response.json()
    assert body["model_used"] == "openai/gpt-5.1"
    assert body["model_alias"] == "smart"
    assert body["fallback_from"] == "anthropic/claude-sonnet-5"
