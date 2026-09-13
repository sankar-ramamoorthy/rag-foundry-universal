# llm_service/tests/api/test_models_endpoint.py
"""
WP-M5 + issue #43: GET /v1/models lists aliases, the default, and named
endpoints with live model inventories (best-effort).
WP-M6: + each provider's discovered catalog (advisory-only, TTL-cached).
"""
import httpx
import pytest
from fastapi.testclient import TestClient

from src.api.v1.main import app
from src.core.model_catalog import reset_catalog_cache

client = TestClient(app)


@pytest.fixture(autouse=True)
def _reset_catalog_cache():
    # WP-M6: the catalog cache is a module-level singleton like the
    # registry -- without a reset, one test's fetch can leak into the
    # next via the TTL (default 3600s, far longer than a test run).
    reset_catalog_cache()
    yield
    reset_catalog_cache()


@pytest.fixture()
def fake_endpoints(monkeypatch):
    """Serve /api/tags for the remote endpoint, and each cloud provider's
    catalog URL; refuse anything else — keeps unit tests off the network
    either way."""

    def handler(request: httpx.Request) -> httpx.Response:
        url = str(request.url)
        if "100.105.24.12" in url:
            return httpx.Response(200, json={"models": [
                {"name": "Qwen3:4b"}, {"name": "deepseek-r1:7b"},
            ]})
        if "openrouter.ai" in url:
            return httpx.Response(200, json={"data": [
                {
                    "id": "meta-llama/llama-3.3-70b-instruct:free",
                    "pricing": {"prompt": "0", "completion": "0"},
                },
                {
                    "id": "openai/gpt-4o",
                    "pricing": {"prompt": "0.000005", "completion": "0.000015"},
                },
            ]})
        if "api.groq.com" in url:
            return httpx.Response(
                200, json={"data": [{"id": "llama-3.1-8b-instant"}]}
            )
        raise httpx.ConnectError("unreachable")

    real_async_client = httpx.AsyncClient

    def patched_client(*args, **kwargs):
        kwargs["transport"] = httpx.MockTransport(handler)
        return real_async_client(*args, **kwargs)

    monkeypatch.setattr(httpx, "AsyncClient", patched_client)


@pytest.fixture()
def no_cloud_keys(monkeypatch):
    """Explicit un-set, regardless of ambient environment/.env, so
    provider `configured` assertions are deterministic."""
    for var in ("GROQ_API_KEY", "OPENROUTER_API_KEY", "NVIDIA_API_KEY"):
        monkeypatch.delenv(var, raising=False)


@pytest.fixture()
def openrouter_key(monkeypatch):
    monkeypatch.setenv("OPENROUTER_API_KEY", "ork-123")


@pytest.fixture()
def remote_env(monkeypatch):
    """Machine-specific remote endpoint activated via env (the way the
    gitignored .env does it); registry reloaded around the test."""
    from src.core.model_registry import reset_registry

    monkeypatch.setenv("REMOTE_OLLAMA_BASE_URL", "http://100.105.24.12:11434")
    reset_registry()
    yield
    reset_registry()


def test_models_endpoint_universal_without_remote_env(fake_endpoints, no_cloud_keys):
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

    # issue #46: Groq/NIM/OpenRouter aliases are always listed (no
    # api_base to env-gate on), unlike the machine-specific remote/
    # summarize entries above -- they only fail at call time without a
    # matching API key.
    assert by_alias["groq_fast"]["model"] == "groq/llama-3.1-8b-instant"
    assert "groq_smart" in by_alias
    assert "groq_reasoning" in by_alias
    assert by_alias["nim_fast"]["model"] == "nvidia_nim/meta/llama3-8b-instruct"
    assert "nim_smart" in by_alias
    assert "openrouter_free" in by_alias

    endpoint_names = {e["name"] for e in body["endpoints"]}
    assert "tailscaleollamalinux" not in endpoint_names
    assert "windowsollamalocal" in endpoint_names
    # nvidia_nim's default api_base is NVIDIA's public endpoint, not a
    # machine-specific address, so unlike tailscaleollamalinux it's
    # always present even without any env var set.
    assert "nvidia_nim" in endpoint_names

    # WP-M6: provider families are always listed (like the Groq/NIM/
    # OpenRouter aliases above); with no credential env vars set, each
    # is unconfigured and the catalog is empty -- no HTTP call attempted.
    providers = {p["name"]: p for p in body["providers"]}
    assert set(providers) == {"groq", "openrouter", "nvidia_nim"}
    for p in providers.values():
        assert p["configured"] is False
        assert p["catalog"] == []
        assert p["catalog_stale"] is False


def test_providers_field_lists_discovered_catalog_when_configured(
    fake_endpoints, no_cloud_keys, openrouter_key
):
    """WP-M6: a configured provider's catalog is discovered live and
    free-tier detection reflects OpenRouter's actual pricing data."""
    body = client.get("/v1/models").json()
    providers = {p["name"]: p for p in body["providers"]}

    assert providers["openrouter"]["configured"] is True
    catalog = {m["id"]: m["free"] for m in providers["openrouter"]["catalog"]}
    assert catalog["meta-llama/llama-3.3-70b-instruct:free"] is True
    assert catalog["openai/gpt-4o"] is False

    # unconfigured providers stay empty, not blocked by openrouter_key
    assert providers["groq"]["configured"] is False
    assert providers["groq"]["catalog"] == []


def test_free_only_filters_provider_catalog_but_not_models_or_endpoints(
    fake_endpoints, no_cloud_keys, openrouter_key
):
    body = client.get("/v1/models?free_only=true").json()
    providers = {p["name"]: p for p in body["providers"]}

    catalog_ids = {m["id"] for m in providers["openrouter"]["catalog"]}
    assert catalog_ids == {"meta-llama/llama-3.3-70b-instruct:free"}

    # the alias menu is untouched by free_only -- no reliable per-request
    # cost signal exists for it the way OpenRouter's pricing field does
    by_alias = {m["alias"]: m for m in body["models"]}
    assert "openrouter_free" in by_alias


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
