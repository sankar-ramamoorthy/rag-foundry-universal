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


@pytest.fixture()
def remote_env(monkeypatch):
    """Machine-specific remote endpoint activated via env (the way the
    gitignored .env does it); registry reloaded around the test."""
    from src.core.model_registry import reset_registry

    monkeypatch.setenv("REMOTE_OLLAMA_BASE_URL", "http://100.105.24.12:11434")
    reset_registry()
    yield
    reset_registry()


def test_models_endpoint_universal_without_remote_env(fake_endpoints):
    """A fresh clone (no remote env vars) sees only universal entries —
    no machine-specific aliases or endpoints."""
    response = client.get("/v1/models")

    assert response.status_code == 200
    body = response.json()
    assert body["default"] == "default"

    by_alias = {m["alias"]: m for m in body["models"]}
    assert by_alias["default"]["is_default"] is True
    assert "local" in by_alias
    assert "smart" in by_alias
    assert "remote" not in by_alias
    assert "summarize" not in by_alias

    endpoint_names = {e["name"] for e in body["endpoints"]}
    assert "tailscaleollamalinux" not in endpoint_names
    assert "windowsollamalocal" in endpoint_names


def test_models_endpoint_with_remote_env(remote_env, fake_endpoints):
    body = client.get("/v1/models").json()

    by_alias = {m["alias"]: m for m in body["models"]}
    assert "remote" in by_alias
    assert "summarize" in by_alias

    endpoints = {e["name"]: e for e in body["endpoints"]}
    # reachable endpoint lists its models, sorted
    assert endpoints["tailscaleollamalinux"]["available_models"] == [
        "Qwen3:4b", "deepseek-r1:7b",
    ]
    # unreachable endpoint degrades to null, menu still renders
    assert endpoints["windowsollamalocal"]["available_models"] is None


def test_summarize_defaults_to_step_alias(remote_env, monkeypatch):
    """issue #43 per-step models: /v1/summarize without params uses the
    `summarize` alias when the remote env activates it."""
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
