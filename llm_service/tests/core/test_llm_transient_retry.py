# llm_service/tests/core/test_llm_transient_retry.py
"""
WP-M8 (issue #125): retry only transient errors on the same candidate
model, with backoff, before generate_completion()'s fallback chain moves
to the next candidate. Confirmed live: a permanent error (404 "model not
found" on an unpulled Ollama model) was burning litellm's blind
num_retries=2 for no benefit, while real transient errors from free-tier
providers (Groq/OpenRouter 429/503) got no backoff at all.
"""
import litellm
import pytest

import src.core.llm_client as llm_client
from src.core.model_registry import ModelRegistry

CONFIG = {
    "models": {
        "primary": "groq/some-model",
        "backup": "openai/gpt-5.1",
    },
    "fallbacks": {"primary": ["backup"]},
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


@pytest.fixture()
def no_real_sleep(monkeypatch):
    """Tests assert on retry/backoff *behavior*, not wall-clock time."""
    sleeps = []

    async def fake_sleep(delay):
        sleeps.append(delay)

    monkeypatch.setattr(llm_client.asyncio, "sleep", fake_sleep)
    return sleeps


async def test_transient_error_retried_in_place_no_fallback(
    registry, monkeypatch, no_real_sleep
):
    attempted_models = []

    async def flaky_then_ok(**kwargs):
        attempted_models.append(kwargs["model"])
        if len(attempted_models) == 1:
            raise litellm.RateLimitError(
                message="rate limited", llm_provider="groq", model=kwargs["model"]
            )
        return _FakeResponse()

    monkeypatch.setattr(llm_client.litellm, "acompletion", flaky_then_ok)

    result = await llm_client.generate_completion(
        context="c", query="q", model="primary"
    )

    # retried the SAME candidate -- no fallback fired
    assert attempted_models == ["groq/some-model", "groq/some-model"]
    assert "fallback_from" not in result
    assert no_real_sleep == [llm_client.RETRY_BACKOFF_BASE_SECONDS]


async def test_transient_error_backs_off_exponentially_then_falls_back(
    registry, monkeypatch, no_real_sleep
):
    async def always_rate_limited(**kwargs):
        raise litellm.RateLimitError(
            message="rate limited", llm_provider="groq", model=kwargs["model"]
        )

    async def ok(**kwargs):
        return _FakeResponse()

    calls = {"n": 0}

    async def dispatch(**kwargs):
        calls["n"] += 1
        if kwargs["model"] == "groq/some-model":
            return await always_rate_limited(**kwargs)
        return await ok(**kwargs)

    monkeypatch.setattr(llm_client.litellm, "acompletion", dispatch)

    result = await llm_client.generate_completion(
        context="c", query="q", model="primary"
    )

    # exhausted MAX_TRANSIENT_RETRIES on the primary, backing off between
    # each attempt, then the existing fallback loop moved on
    assert no_real_sleep == [
        llm_client.RETRY_BACKOFF_BASE_SECONDS * (2**attempt)
        for attempt in range(llm_client.MAX_TRANSIENT_RETRIES)
    ]
    assert result["fallback_from"] == "groq/some-model"
    assert result["model"] == "openai/gpt-5.1"


async def test_permanent_error_never_retried_falls_back_immediately(
    registry, monkeypatch, no_real_sleep
):
    attempted_models = []

    async def not_found_then_ok(**kwargs):
        attempted_models.append(kwargs["model"])
        if kwargs["model"] == "groq/some-model":
            raise litellm.NotFoundError(
                message="model not found",
                model=kwargs["model"],
                llm_provider="groq",
            )
        return _FakeResponse()

    monkeypatch.setattr(llm_client.litellm, "acompletion", not_found_then_ok)

    result = await llm_client.generate_completion(
        context="c", query="q", model="primary"
    )

    # exactly one attempt at the broken candidate -- no retry -- then fallback
    assert attempted_models == ["groq/some-model", "openai/gpt-5.1"]
    assert no_real_sleep == []
    assert result["fallback_from"] == "groq/some-model"
