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


# ------------------------------------------------------------------
# issue #43: env interpolation + named endpoints
# ------------------------------------------------------------------

ENDPOINT_CONFIG = {
    "models": {
        "default": {
            "model": "ollama/${TEST_REMOTE_MODEL:Qwen3:4b}",
            "api_base": "${TEST_REMOTE_BASE:http://100.105.24.12:11434}",
            "timeout": 300,
        },
        "local": {"model": "ollama/phi4-mini:latest"},
    },
    "endpoints": {
        "tailscaleollamalinux": {
            "provider": "ollama",
            "api_base": "${TEST_REMOTE_BASE:http://100.105.24.12:11434}",
            "timeout": 300,
        },
        "windowsollamalocal": {
            "provider": "ollama",
            "api_base": "http://host.docker.internal:11434",
        },
    },
    "fallbacks": {
        "default": ["local"],
        "tailscaleollamalinux": ["local"],
    },
    "timeouts": {"default": 600},
}


def test_env_interpolation_uses_defaults_with_colons():
    registry = ModelRegistry(ENDPOINT_CONFIG)
    resolved = registry.resolve(None, None)
    # defaults after the first colon survive intact (model tags, URLs)
    assert resolved.model == "ollama/Qwen3:4b"
    assert resolved.api_base == "http://100.105.24.12:11434"


def test_env_interpolation_prefers_environment(monkeypatch):
    monkeypatch.setenv("TEST_REMOTE_MODEL", "deepseek-r1:7b")
    monkeypatch.setenv("TEST_REMOTE_BASE", "http://10.0.0.9:11434")
    registry = ModelRegistry(ENDPOINT_CONFIG)
    resolved = registry.resolve(None, None)
    assert resolved.model == "ollama/deepseek-r1:7b"
    assert resolved.api_base == "http://10.0.0.9:11434"


def test_endpoint_prefixed_model_routes_to_endpoint():
    """The user picks tailscaleollamalinux plus any model they believe
    is available there — no pre-registration required."""
    registry = ModelRegistry(ENDPOINT_CONFIG)
    resolved = registry.resolve(None, "tailscaleollamalinux/qwen2.5-coder:latest")
    assert resolved.model == "ollama/qwen2.5-coder:latest"
    assert resolved.api_base == "http://100.105.24.12:11434"
    assert resolved.alias == "tailscaleollamalinux"
    assert resolved.timeout == 300.0


def test_endpoint_name_keys_fallback_chain():
    registry = ModelRegistry(ENDPOINT_CONFIG)
    primary = registry.resolve(None, "tailscaleollamalinux/Qwen3:8b")
    chain = registry.fallback_chain(primary)
    assert [c.model for c in chain] == [
        "ollama/Qwen3:8b",
        "ollama/phi4-mini:latest",
    ]


def test_remote_default_falls_back_to_local():
    registry = ModelRegistry(ENDPOINT_CONFIG)
    chain = registry.fallback_chain(registry.resolve(None, None))
    assert [c.model for c in chain] == [
        "ollama/Qwen3:4b",
        "ollama/phi4-mini:latest",
    ]
    # local fallback keeps the Windows-host api_base default
    assert chain[1].api_base == OLLAMA_BASE_URL


def test_unknown_prefix_still_passes_through_as_raw():
    registry = ModelRegistry(ENDPOINT_CONFIG)
    resolved = registry.resolve(None, "groq/llama-3.1-8b-instant")
    assert resolved.alias is None
    assert resolved.model == "groq/llama-3.1-8b-instant"
    assert resolved.api_base is None


def test_describe_endpoints_shape():
    registry = ModelRegistry(ENDPOINT_CONFIG)
    endpoints = {e["name"]: e for e in registry.describe_endpoints()}
    assert endpoints["tailscaleollamalinux"]["provider"] == "ollama"
    assert endpoints["tailscaleollamalinux"]["api_base"] == (
        "http://100.105.24.12:11434"
    )
    assert "windowsollamalocal" in endpoints


def test_empty_api_base_entries_are_pruned():
    """Machine-specific entries with an unset env var (empty api_base)
    must not exist — the committed yaml stays universal."""
    registry = ModelRegistry({
        "models": {
            "local": "ollama/phi4-mini:latest",
            "remote": {"model": "ollama/big", "api_base": "${UNSET_XYZ_VAR:}"},
        },
        "endpoints": {
            "tail": {"provider": "ollama", "api_base": "${UNSET_XYZ_VAR:}"},
        },
    })
    assert not registry.has_alias("remote")
    assert registry.describe_endpoints() == []
    # default falls back to the built-in local derivation
    assert registry.resolve(None, None).model == f"ollama/{OLLAMA_MODEL}"


def test_llm_default_alias_promotes_remote(monkeypatch):
    monkeypatch.setenv("PROMO_BASE_XYZ", "http://gpu-box:11434")
    monkeypatch.setenv("LLM_DEFAULT_ALIAS", "remote")
    registry = ModelRegistry({
        "models": {
            "local": "ollama/phi4-mini:latest",
            "remote": {"model": "ollama/big", "api_base": "${PROMO_BASE_XYZ:}"},
        },
        "fallbacks": {"default": ["local"]},
    })
    resolved = registry.resolve(None, None)
    assert resolved.model == "ollama/big"
    assert resolved.api_base == "http://gpu-box:11434"
    chain = registry.fallback_chain(resolved)
    assert [c.model for c in chain] == ["ollama/big", "ollama/phi4-mini:latest"]


def test_llm_default_alias_ignored_when_target_pruned(monkeypatch):
    """LLM_DEFAULT_ALIAS=remote without the remote base URL set must not
    break the default route."""
    monkeypatch.setenv("LLM_DEFAULT_ALIAS", "remote")
    registry = ModelRegistry({
        "models": {
            "local": "ollama/phi4-mini:latest",
            "remote": {"model": "ollama/big", "api_base": "${UNSET_XYZ_VAR:}"},
        },
    })
    assert registry.resolve(None, None).model == f"ollama/{OLLAMA_MODEL}"
