# llm_service/tests/core/test_llm_resilience.py
"""
WP-M2: fallbacks, retries, timeouts — outages degrade gracefully.
"""
import pytest
from fastapi.testclient import TestClient

import src.core.llm_client as llm_client
from src.api.v1.main import app
from src.core.llm_client import AllProvidersFailedError
from src.core.model_registry import ModelRegistry

CONFIG = {
    "models": {
        "primary": "anthropic/claude-sonnet-5",
        "backup": "openai/gpt-5.1",
        "slow": {"model": "ollama/llama3:70b", "timeout": 300},
    },
    "fallbacks": {
        "primary": ["backup", "missing-alias", "slow"],
    },
    "timeouts": {"default": 120},
}


class _FakeMessage:
    content = "answer"


class _FakeChoice:
    message = _FakeMessage()


class _FakeResponse:
    choices = [_FakeChoice()]
    usage = None


@pytest.fixture()
def registry(monkeypatch):
    reg = ModelRegistry(CONFIG)
    monkeypatch.setattr(llm_client, "get_registry", lambda: reg)
    return reg


def test_fallback_chain_order_skips_unknown_and_dedupes(registry):
    primary = registry.resolve(None, "primary")
    chain = registry.fallback_chain(primary)
    assert [c.model for c in chain] == [
        "anthropic/claude-sonnet-5",
        "openai/gpt-5.1",
        "ollama/llama3:70b",
    ]


def test_raw_model_has_no_fallbacks(registry):
    primary = registry.resolve(None, "mistral/mistral-large")
    assert [c.model for c in registry.fallback_chain(primary)] == [
        "mistral/mistral-large"
    ]


async def test_primary_failure_answers_from_fallback(registry, monkeypatch):
    attempted = []

    async def flaky_acompletion(**kwargs):
        attempted.append(kwargs["model"])
        if kwargs["model"] == "anthropic/claude-sonnet-5":
            raise RuntimeError("provider down")
        return _FakeResponse()

    monkeypatch.setattr(llm_client.litellm, "acompletion", flaky_acompletion)

    result = await llm_client.generate_completion(
        context="c", query="q", model="primary"
    )

    assert attempted == ["anthropic/claude-sonnet-5", "openai/gpt-5.1"]
    # the response names the model actually used, and where it fell from
    assert result["model"] == "openai/gpt-5.1"
    assert result["fallback_from"] == "anthropic/claude-sonnet-5"
    assert result["response"] == "answer"


async def test_no_fallback_marker_on_primary_success(registry, monkeypatch):
    async def ok_acompletion(**kwargs):
        return _FakeResponse()

    monkeypatch.setattr(llm_client.litellm, "acompletion", ok_acompletion)

    result = await llm_client.generate_completion(
        context="c", query="q", model="primary"
    )
    assert "fallback_from" not in result


async def test_all_providers_down_raises_actionable_error(
    registry, monkeypatch
):
    async def dead_acompletion(**kwargs):
        raise RuntimeError("connection refused")

    monkeypatch.setattr(llm_client.litellm, "acompletion", dead_acompletion)

    with pytest.raises(AllProvidersFailedError) as exc_info:
        await llm_client.generate_completion(
            context="c", query="q", model="primary"
        )

    err = exc_info.value
    assert err.attempted == [
        "anthropic/claude-sonnet-5",
        "openai/gpt-5.1",
        "ollama/llama3:70b",
    ]
    assert "connection refused" in str(err)


async def test_per_model_timeout_and_retries_passed(registry, monkeypatch):
    captured = []

    async def failing_then_ok(**kwargs):
        captured.append((kwargs["model"], kwargs["timeout"], kwargs["num_retries"]))
        if len(captured) < 3:
            raise RuntimeError("down")
        return _FakeResponse()

    monkeypatch.setattr(llm_client.litellm, "acompletion", failing_then_ok)

    await llm_client.generate_completion(context="c", query="q", model="primary")

    # each candidate carries its own timeout; retries delegated to LiteLLM
    assert captured == [
        ("anthropic/claude-sonnet-5", 120.0, llm_client.NUM_RETRIES),
        ("openai/gpt-5.1", 120.0, llm_client.NUM_RETRIES),
        ("ollama/llama3:70b", 300.0, llm_client.NUM_RETRIES),
    ]


def test_endpoint_returns_503_when_all_providers_fail(monkeypatch):
    async def fake_generate(**kwargs):
        raise AllProvidersFailedError(
            ["anthropic/claude-sonnet-5", "openai/gpt-5.1"],
            RuntimeError("connection refused"),
        )

    monkeypatch.setattr(
        "src.api.v1.main.generate_completion", fake_generate
    )

    client = TestClient(app)
    response = client.post("/generate", json={"query": "q"})

    assert response.status_code == 503
    body = response.json()
    assert "All configured LLM providers failed" in body["error"]
    assert body["attempted_models"] == [
        "anthropic/claude-sonnet-5",
        "openai/gpt-5.1",
    ]
