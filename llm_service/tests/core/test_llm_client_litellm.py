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


async def test_no_params_uses_local_ollama_default(capture):
    """Universal default for a fresh clone: with no remote env vars set,
    /generate answers via the host-local Ollama exactly as before."""
    result = await llm_client.generate_completion(context="c", query="q")

    assert capture["model"] == f"ollama/{OLLAMA_MODEL}"
    assert capture["api_base"] == OLLAMA_BASE_URL
    assert result["provider"] == "ollama"
    assert result["response"] == "the answer"


async def test_remote_env_promotes_remote_default(capture, monkeypatch):
    """issue #43: setting REMOTE_OLLAMA_BASE_URL + LLM_DEFAULT_ALIAS in
    the (gitignored) .env makes the remote box the default route —
    machine-specific config, never committed."""
    from src.core.model_registry import reset_registry

    monkeypatch.setenv("REMOTE_OLLAMA_BASE_URL", "http://100.105.24.12:11434")
    monkeypatch.setenv("LLM_DEFAULT_ALIAS", "remote")
    reset_registry()
    try:
        result = await llm_client.generate_completion(context="c", query="q")
        assert capture["model"] == "ollama/Qwen3:4b"
        assert capture["api_base"] == "http://100.105.24.12:11434"
        assert result["model_alias"] == "default"
    finally:
        reset_registry()


async def test_local_alias_targets_host_ollama(capture):
    await llm_client.generate_completion(context="c", query="q", model="local")

    assert capture["model"] == f"ollama/{OLLAMA_MODEL}"
    assert capture["api_base"] == OLLAMA_BASE_URL


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
