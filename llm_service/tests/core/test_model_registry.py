# llm_service/tests/core/test_model_registry.py
"""
WP-M1: alias resolution rules of the model registry.
"""
import pytest

from src.core.config import OLLAMA_BASE_URL, OLLAMA_MODEL
from src.core.model_registry import (
    ModelRegistry,
    UnknownModelAliasError,
)

CONFIG = {
    "models": {
        "fast": "anthropic/claude-haiku-4-5",
        "smart": "anthropic/claude-sonnet-5",
        "local-big": {
            "model": "ollama/llama3:70b",
            "api_base": "http://gpu-box.tailnet:11434",
            "timeout": 300,
        },
    },
    "fallbacks": {"smart": ["fast", "default"]},
    "timeouts": {"default": 120, "fast": 30},
}


@pytest.fixture()
def registry():
    return ModelRegistry(CONFIG)


def test_no_params_resolves_to_ollama_default(registry):
    resolved = registry.resolve(None, None)
    assert resolved.alias == "default"
    assert resolved.model == f"ollama/{OLLAMA_MODEL}"
    assert resolved.api_base == OLLAMA_BASE_URL


def test_alias_resolves_to_model_string(registry):
    resolved = registry.resolve(None, "smart")
    assert resolved.alias == "smart"
    assert resolved.model == "anthropic/claude-sonnet-5"
    assert resolved.api_base is None


def test_raw_litellm_string_passes_through(registry):
    resolved = registry.resolve(None, "anthropic/claude-sonnet-5")
    assert resolved.alias is None
    assert resolved.model == "anthropic/claude-sonnet-5"


def test_legacy_provider_model_pair_maps(registry):
    resolved = registry.resolve("ollama", "phi4-mini:latest")
    assert resolved.model == "ollama/phi4-mini:latest"
    assert resolved.api_base == OLLAMA_BASE_URL


def test_legacy_ollama_provider_without_model(registry):
    resolved = registry.resolve("ollama", None)
    assert resolved.model == f"ollama/{OLLAMA_MODEL}"


def test_non_ollama_provider_without_model_raises(registry):
    with pytest.raises(ValueError, match="Unsupported LLM provider"):
        registry.resolve("openai", None)


def test_unknown_alias_raises_with_menu(registry):
    with pytest.raises(UnknownModelAliasError) as exc_info:
        registry.resolve(None, "bogus")
    assert "bogus" in str(exc_info.value)
    assert "smart" in exc_info.value.valid_aliases
    assert "default" in exc_info.value.valid_aliases


def test_endpoint_mapping_alias_carries_api_base_and_timeout(registry):
    """Multi-endpoint requirement: a second Ollama endpoint (e.g. the
    Tailscale GPU box) is pure config — no code changes."""
    resolved = registry.resolve(None, "local-big")
    assert resolved.model == "ollama/llama3:70b"
    assert resolved.api_base == "http://gpu-box.tailnet:11434"
    assert resolved.timeout == 300.0


def test_per_alias_timeout_from_timeouts_map(registry):
    assert registry.resolve(None, "fast").timeout == 30.0
    assert registry.resolve(None, "smart").timeout == 120.0


def test_describe_lists_aliases_with_default_flag(registry):
    menu = registry.describe()
    aliases = {entry["alias"]: entry for entry in menu}
    assert aliases["default"]["is_default"] is True
    assert aliases["smart"]["is_default"] is False
