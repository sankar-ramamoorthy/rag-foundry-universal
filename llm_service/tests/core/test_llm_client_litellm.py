# llm_service/tests/core/test_llm_client_litellm.py
"""
WP-M1: generate_completion drives litellm.acompletion.

Replaces the pre-LiteLLM tests that locked the raw Ollama HTTP shape and
the old context-stuffed prompt — the message structure (system + user)
and the LiteLLM call contract are the new locked surface.
"""
import pytest

import src.core.llm_client as llm_client
from src.core.config import OLLAMA_BASE_URL, OLLAMA_MODEL
from src.core.prompts import PROMPT_TEMPLATE_VERSION


class _FakeUsage:
    prompt_tokens = 10
    completion_tokens = 5
    total_tokens = 15


class _FakeMessage:
    content = " the answer "


class _FakeChoice:
    message = _FakeMessage()


class _FakeResponse:
    choices = [_FakeChoice()]
    usage = _FakeUsage()


@pytest.fixture()
def capture(monkeypatch):
    calls = {}

    async def fake_acompletion(**kwargs):
        calls.update(kwargs)
        return _FakeResponse()

    monkeypatch.setattr(llm_client.litellm, "acompletion", fake_acompletion)
    return calls


async def test_no_params_uses_ollama_default_as_before(capture):
    """Regression: /generate with no params answers via Ollama exactly
    as before the LiteLLM swap."""
    result = await llm_client.generate_completion(context="c", query="q")

    assert capture["model"] == f"ollama/{OLLAMA_MODEL}"
    assert capture["api_base"] == OLLAMA_BASE_URL
    assert result["provider"] == "ollama"
    assert result["response"] == "the answer"


async def test_messages_carry_system_and_user_roles(capture):
    await llm_client.generate_completion(context="CTX", query="QUESTION")

    messages = capture["messages"]
    assert [m["role"] for m in messages] == ["system", "user"]
    assert "CTX" in messages[1]["content"]
    assert "QUESTION" in messages[1]["content"]


async def test_alias_routes_to_aliased_model(capture):
    """`model=smart` (from llm_service/models.yaml) routes to the
    aliased LiteLLM model string."""
    result = await llm_client.generate_completion(
        context="c", query="q", model="smart"
    )
    assert capture["model"] == "anthropic/claude-sonnet-5"
    assert result["model_alias"] == "smart"


async def test_raw_model_string_passes_through(capture):
    await llm_client.generate_completion(
        context="c", query="q", model="anthropic/claude-sonnet-5"
    )
    assert capture["model"] == "anthropic/claude-sonnet-5"


async def test_response_includes_usage_and_template_version(capture):
    result = await llm_client.generate_completion(context="c", query="q")

    assert result["usage"] == {
        "prompt_tokens": 10,
        "completion_tokens": 5,
        "total_tokens": 15,
    }
    assert result["prompt_template"] == PROMPT_TEMPLATE_VERSION


async def test_unsupported_provider_without_model_raises(capture):
    with pytest.raises(ValueError, match="Unsupported LLM provider"):
        await llm_client.generate_completion(
            context="x", query="y", provider="openai"
        )
