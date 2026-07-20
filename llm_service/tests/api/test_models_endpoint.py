# llm_service/tests/api/test_models_endpoint.py
"""
WP-M5 + issue #43: GET /v1/models lists aliases, the default, and named
endpoints with live model inventories (best-effort).
"""
import httpx
import pytest
from fastapi.testclient import TestClient

from src.api.v1.main import app

client = TestClient(app)


@pytest.fixture()
def fake_endpoints(monkeypatch):
    """Serve /api/tags for the remote endpoint; refuse the local one —
    keeps unit tests off the network either way."""

    def handler(request: httpx.Request) -> httpx.Response:
        if "100.105.24.12" in str(request.url):
            return httpx.Response(200, json={"models": [
                {"name": "Qwen3:4b"}, {"name": "deepseek-r1:7b"},
            ]})
        raise httpx.ConnectError("unreachable")

    real_async_client = httpx.AsyncClient

    def patched_client(*args, **kwargs):
        kwargs["transport"] = httpx.MockTransport(handler)
        return real_async_client(*args, **kwargs)

    monkeypatch.setattr(httpx, "AsyncClient", patched_client)


def test_models_endpoint_lists_aliases_with_default(fake_endpoints):
    response = client.get("/v1/models")

    assert response.status_code == 200
    body = response.json()
    assert body["default"] == "default"

    by_alias = {m["alias"]: m for m in body["models"]}
    assert by_alias["default"]["is_default"] is True
    assert by_alias["default"]["model"] == "ollama/Qwen3:4b"
    assert "local" in by_alias
    assert "summarize" in by_alias
    assert "smart" in by_alias
    assert by_alias["smart"]["model"] == "anthropic/claude-sonnet-5"
    assert by_alias["smart"]["is_default"] is False


def test_models_endpoint_reports_live_endpoint_inventory(fake_endpoints):
    body = client.get("/v1/models").json()
    endpoints = {e["name"]: e for e in body["endpoints"]}

    # reachable endpoint lists its models, sorted
    assert endpoints["tailscaleollamalinux"]["available_models"] == [
        "Qwen3:4b", "deepseek-r1:7b",
    ]
    # unreachable endpoint degrades to null, menu still renders
    assert endpoints["windowsollamalocal"]["available_models"] is None


def test_summarize_defaults_to_step_alias(monkeypatch):
    """issue #43 per-step models: /v1/summarize without params uses the
    `summarize` alias from models.yaml."""
    captured = {}

    async def fake_fetch_chunks(ingestion_id):
        return ["chunk text"]

    async def fake_update(ingestion_id, summary):
        return None

    async def fake_generate(**kwargs):
        captured.update(kwargs)
        return {"response": "a summary"}

    monkeypatch.setattr("src.api.v1.summarize.fetch_chunks", fake_fetch_chunks)
    monkeypatch.setattr(
        "src.api.v1.summarize.update_document_summary", fake_update
    )
    monkeypatch.setattr(
        "src.api.v1.summarize.generate_completion", fake_generate
    )

    response = client.post(
        "/v1/summarize/123e4567-e89b-12d3-a456-426614174000"
    )

    assert response.status_code == 200
    assert captured["model"] == "summarize"


def test_summarize_forwards_model_alias(monkeypatch):
    """WP-M5: /v1/summarize honors the model param instead of the old
    hardcoded phi4-mini."""
    captured = {}

    async def fake_fetch_chunks(ingestion_id):
        return ["chunk text"]

    async def fake_update(ingestion_id, summary):
        return None

    async def fake_generate(**kwargs):
        captured.update(kwargs)
        return {"response": "a summary"}

    monkeypatch.setattr("src.api.v1.summarize.fetch_chunks", fake_fetch_chunks)
    monkeypatch.setattr(
        "src.api.v1.summarize.update_document_summary", fake_update
    )
    monkeypatch.setattr(
        "src.api.v1.summarize.generate_completion", fake_generate
    )

    response = client.post(
        "/v1/summarize/123e4567-e89b-12d3-a456-426614174000?model=smart"
    )

    assert response.status_code == 200
    assert captured["model"] == "smart"
    assert response.json()["summary"] == "a summary"
