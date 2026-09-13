# llm_service/tests/core/test_model_catalog.py
"""
WP-M6: dynamic model catalog -- advisory/observational only.
"""
import httpx
import pytest

from src.core import model_catalog


@pytest.fixture(autouse=True)
def _reset_cache():
    model_catalog.reset_catalog_cache()
    yield
    model_catalog.reset_catalog_cache()


def _mock_transport(handler):
    real_async_client = httpx.AsyncClient

    def patched_client(*args, **kwargs):
        kwargs["transport"] = httpx.MockTransport(handler)
        return real_async_client(*args, **kwargs)

    return patched_client


@pytest.fixture()
def groq_key(monkeypatch):
    monkeypatch.setenv("TEST_GROQ_KEY", "gk-123")


@pytest.fixture()
def openrouter_key(monkeypatch):
    monkeypatch.setenv("TEST_OPENROUTER_KEY", "ork-123")


async def test_unconfigured_provider_skips_http_call(monkeypatch):
    """No credential env var set -> configured False, no HTTP attempted."""
    called = {"count": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        called["count"] += 1
        return httpx.Response(200, json={"data": []})

    monkeypatch.setattr(httpx, "AsyncClient", _mock_transport(handler))

    models, stale, configured = await model_catalog.get_catalog(
        "groq",
        "groq",
        {"credential_env": "UNSET_GROQ_KEY_XYZ", "catalog_url": "https://x/models"},
    )
    assert models == []
    assert stale is False
    assert configured is False
    assert called["count"] == 0


async def test_openrouter_free_detection_from_pricing(openrouter_key, monkeypatch):
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.headers["authorization"] == "Bearer ork-123"
        return httpx.Response(
            200,
            json={
                "data": [
                    {
                        "id": "meta-llama/llama-3.3-70b-instruct:free",
                        "pricing": {"prompt": "0", "completion": "0"},
                    },
                    {
                        "id": "openai/gpt-4o",
                        "pricing": {"prompt": "0.000005", "completion": "0.000015"},
                    },
                ]
            },
        )

    monkeypatch.setattr(httpx, "AsyncClient", _mock_transport(handler))

    models, stale, configured = await model_catalog.get_catalog(
        "openrouter",
        "openrouter",
        {
            "credential_env": "TEST_OPENROUTER_KEY",
            "catalog_url": "https://openrouter.ai/api/v1/models",
        },
    )
    assert stale is False
    assert configured is True
    by_id = {m.id: m for m in models}
    assert by_id["meta-llama/llama-3.3-70b-instruct:free"].free is True
    assert by_id["openai/gpt-4o"].free is False


async def test_groq_entries_have_null_free_not_guessed(groq_key, monkeypatch):
    """Groq's /models response carries no pricing signal -- free must be
    None (unknown), never inferred as True or False."""

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200, json={"data": [{"id": "llama-3.1-8b-instant"}]}
        )

    monkeypatch.setattr(httpx, "AsyncClient", _mock_transport(handler))

    models, _, configured = await model_catalog.get_catalog(
        "groq",
        "groq",
        {"credential_env": "TEST_GROQ_KEY", "catalog_url": "https://x/models"},
    )
    assert configured is True
    assert models == [model_catalog.CatalogEntry(id="llama-3.1-8b-instant", free=None)]


async def test_fetch_failure_degrades_to_last_known_good(groq_key, monkeypatch):
    calls = {"n": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        calls["n"] += 1
        if calls["n"] == 1:
            return httpx.Response(200, json={"data": [{"id": "model-a"}]})
        raise httpx.ConnectError("boom")

    monkeypatch.setattr(httpx, "AsyncClient", _mock_transport(handler))
    entry = {"credential_env": "TEST_GROQ_KEY", "catalog_url": "https://x/models"}

    first_models, first_stale, _ = await model_catalog.get_catalog(
        "groq", "groq", entry
    )
    assert first_stale is False
    assert first_models[0].id == "model-a"

    second_models, second_stale, second_configured = await model_catalog.get_catalog(
        "groq", "groq", entry, force=True
    )
    assert second_stale is True
    assert second_configured is True
    assert second_models[0].id == "model-a"  # unchanged, not silently emptied


async def test_no_prior_cache_and_fetch_fails_returns_empty_not_raise(
    groq_key, monkeypatch
):
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("boom")

    monkeypatch.setattr(httpx, "AsyncClient", _mock_transport(handler))

    models, stale, configured = await model_catalog.get_catalog(
        "groq",
        "groq",
        {"credential_env": "TEST_GROQ_KEY", "catalog_url": "https://x/models"},
    )
    assert models == []
    assert stale is False
    assert configured is True


async def test_ttl_cache_avoids_refetch_within_window(groq_key, monkeypatch):
    calls = {"n": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        calls["n"] += 1
        return httpx.Response(200, json={"data": [{"id": "model-a"}]})

    monkeypatch.setattr(httpx, "AsyncClient", _mock_transport(handler))
    entry = {"credential_env": "TEST_GROQ_KEY", "catalog_url": "https://x/models"}

    await model_catalog.get_catalog("groq", "groq", entry)
    await model_catalog.get_catalog("groq", "groq", entry)
    assert calls["n"] == 1


async def test_ttl_expiry_triggers_refetch(groq_key, monkeypatch):
    calls = {"n": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        calls["n"] += 1
        return httpx.Response(200, json={"data": [{"id": "model-a"}]})

    monkeypatch.setattr(httpx, "AsyncClient", _mock_transport(handler))
    monkeypatch.setattr(model_catalog, "MODEL_CATALOG_TTL_SECONDS", 0)
    entry = {"credential_env": "TEST_GROQ_KEY", "catalog_url": "https://x/models"}

    await model_catalog.get_catalog("groq", "groq", entry)
    await model_catalog.get_catalog("groq", "groq", entry)
    assert calls["n"] == 2


async def test_ollama_fetch_uses_tags_endpoint(monkeypatch):
    def handler(request: httpx.Request) -> httpx.Response:
        assert str(request.url).endswith("/api/tags")
        return httpx.Response(
            200, json={"models": [{"name": "Qwen3:4b"}, {"name": "deepseek-r1:7b"}]}
        )

    monkeypatch.setattr(httpx, "AsyncClient", _mock_transport(handler))

    models, stale, configured = await model_catalog.get_catalog(
        "tailscaleollamalinux",
        "ollama",
        {"api_base": "http://100.105.24.12:11434"},
    )
    assert stale is False
    assert configured is True
    assert [m.id for m in models] == ["Qwen3:4b", "deepseek-r1:7b"]
    assert all(m.free is None for m in models)


async def test_unknown_provider_returns_empty_configured_true():
    models, stale, configured = await model_catalog.get_catalog(
        "mystery", "mystery-provider", {}
    )
    assert models == []
    assert stale is False
    assert configured is True
