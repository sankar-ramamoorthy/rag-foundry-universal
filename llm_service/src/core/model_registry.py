# llm_service/src/core/model_registry.py
"""
Model registry (WP-M1): friendly aliases -> LiteLLM model strings.

The registry lives in models.yaml (path via MODELS_CONFIG_PATH), not in
code, so the model menu — including additional inference endpoints with
their own api_base (e.g. a remote Ollama box) — changes without an
application deploy. An alias value is either a plain LiteLLM string:

    fast: anthropic/claude-haiku-4-5

or a mapping for endpoint-specific routing:

    local-big:
      model: ollama/llama3:70b
      api_base: http://gpu-box.tailnet:11434
      timeout: 300

Named endpoints (issue #43) let a user route an arbitrary model to a
specific inference host — "pick tailscaleollamalinux and whatever model
is available there" — without pre-registering every model:

    endpoints:
      tailscaleollamalinux:
        provider: ollama
        api_base: http://100.105.24.12:11434
        timeout: 300

makes `model=tailscaleollamalinux/Qwen3:8b` resolve to
`ollama/Qwen3:8b` at that api_base. Endpoint names also work as keys in
`fallbacks`, so an endpoint can degrade to an alias when unreachable.

Every string value in models.yaml supports `${VAR}` / `${VAR:default}`
environment interpolation, so machine-specific addresses stay
overridable without editing committed config.

Resolution order for an incoming request:
alias -> endpoint-prefixed (`<endpoint>/<model>`) -> raw LiteLLM string
(contains "/") -> legacy (provider, model) pair -> error listing valid
aliases. The `default` alias, when absent from the yaml, derives from
OLLAMA_MODEL to preserve pre-LiteLLM behavior.
"""
from __future__ import annotations

import os
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional

import yaml

from src.core.config import LLM_TIMEOUT, OLLAMA_BASE_URL, OLLAMA_MODEL

DEFAULT_ALIAS = "default"

# ${VAR} or ${VAR:default} — the default may itself contain colons
# (model tags like phi4-mini:latest, URLs like http://host:11434).
_ENV_PATTERN = re.compile(r"\$\{([A-Za-z_][A-Za-z0-9_]*)(?::([^}]*))?\}")


def _interpolate_env(value: Any) -> Any:
    """Recursively substitute ${VAR}/${VAR:default} in string values."""
    if isinstance(value, str):
        return _ENV_PATTERN.sub(
            lambda m: os.getenv(m.group(1), m.group(2) or ""), value
        )
    if isinstance(value, dict):
        return {k: _interpolate_env(v) for k, v in value.items()}
    if isinstance(value, list):
        return [_interpolate_env(v) for v in value]
    return value


class UnknownModelAliasError(ValueError):
    """Raised when `model` is neither an alias nor a raw LiteLLM string."""

    def __init__(self, requested: str, valid_aliases: List[str]):
        self.requested = requested
        self.valid_aliases = valid_aliases
        super().__init__(
            f"Unknown model alias '{requested}'. "
            f"Valid aliases: {', '.join(valid_aliases)}. "
            "Raw LiteLLM strings (provider/model) also pass through."
        )


@dataclass(frozen=True)
class ResolvedModel:
    alias: Optional[str]
    model: str
    api_base: Optional[str]
    timeout: float


class ModelRegistry:
    def __init__(self, config: Dict[str, Any]):
        config = _interpolate_env(config)
        raw_models = config.get("models") or {}
        self._aliases: Dict[str, Dict[str, Any]] = {}
        for alias, value in raw_models.items():
            if isinstance(value, str):
                self._aliases[alias] = {"model": value}
            elif isinstance(value, dict) and "model" in value:
                self._aliases[alias] = dict(value)
        if DEFAULT_ALIAS not in self._aliases:
            self._aliases[DEFAULT_ALIAS] = {"model": f"ollama/{OLLAMA_MODEL}"}

        # issue #43: named inference endpoints for arbitrary-model routing
        self._endpoints: Dict[str, Dict[str, Any]] = {}
        for name, value in (config.get("endpoints") or {}).items():
            if isinstance(value, dict) and "api_base" in value:
                self._endpoints[name] = dict(value)

        self.fallbacks: Dict[str, List[str]] = config.get("fallbacks") or {}
        self._timeouts: Dict[str, Any] = config.get("timeouts") or {}

    # ------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------

    def aliases(self) -> List[str]:
        return sorted(self._aliases)

    def has_alias(self, name: str) -> bool:
        return name in self._aliases

    def describe(self) -> List[Dict[str, Any]]:
        """Alias menu for GET /v1/models (WP-M5)."""
        return [
            {
                "alias": alias,
                "model": self._aliases[alias]["model"],
                "is_default": alias == DEFAULT_ALIAS,
            }
            for alias in self.aliases()
        ]

    def describe_endpoints(self) -> List[Dict[str, Any]]:
        """Named endpoints for GET /v1/models (issue #43). The caller
        may enrich each entry with live model listings."""
        return [
            {
                "name": name,
                "provider": entry.get("provider", "ollama"),
                "api_base": entry["api_base"],
            }
            for name, entry in sorted(self._endpoints.items())
        ]

    def fallback_chain(self, primary: ResolvedModel) -> List[ResolvedModel]:
        """WP-M2: the ordered attempt chain for a resolved model —
        the primary first, then its configured fallback aliases.
        Unknown fallback aliases are skipped; duplicates collapse.
        Non-alias resolutions (raw strings, legacy pairs) have no
        fallbacks."""
        chain = [primary]
        seen = {primary.model}
        if primary.alias:
            for fallback_alias in self.fallbacks.get(primary.alias, []):
                if fallback_alias not in self._aliases:
                    continue
                candidate = self._from_alias(fallback_alias)
                if candidate.model in seen:
                    continue
                seen.add(candidate.model)
                chain.append(candidate)
        return chain

    def resolve(
        self, provider: Optional[str], model: Optional[str]
    ) -> ResolvedModel:
        if model is None:
            if provider is None:
                return self._from_alias(DEFAULT_ALIAS)
            if provider == "ollama":
                return self._finalize(None, f"ollama/{OLLAMA_MODEL}", {})
            raise ValueError(
                f"Unsupported LLM provider without an explicit model: "
                f"{provider}"
            )

        if model in self._aliases:
            return self._from_alias(model)

        if "/" in model:
            prefix, remainder = model.split("/", 1)
            if prefix in self._endpoints and remainder:
                # issue #43: `<endpoint>/<any model>` routes the model to
                # that endpoint's api_base — the user picks whatever they
                # believe is available there. The endpoint name doubles
                # as the alias so fallbacks/timeouts keyed by it apply.
                entry = self._endpoints[prefix]
                litellm_provider = entry.get("provider", "ollama")
                return self._finalize(
                    prefix, f"{litellm_provider}/{remainder}", entry
                )
            # raw LiteLLM string passes through verbatim
            return self._finalize(None, model, {})

        if provider:
            # legacy (provider, model) pair -> "provider/model"
            return self._finalize(None, f"{provider}/{model}", {})

        raise UnknownModelAliasError(model, self.aliases())

    # ------------------------------------------------------------
    # Internals
    # ------------------------------------------------------------

    def _from_alias(self, alias: str) -> ResolvedModel:
        entry = self._aliases[alias]
        return self._finalize(alias, entry["model"], entry)

    def _finalize(
        self, alias: Optional[str], model: str, entry: Dict[str, Any]
    ) -> ResolvedModel:
        api_base = entry.get("api_base")
        if api_base is None and model.startswith("ollama/"):
            api_base = OLLAMA_BASE_URL

        timeout = entry.get("timeout")
        if timeout is None and alias is not None:
            timeout = self._timeouts.get(alias)
        if timeout is None:
            timeout = self._timeouts.get("default", LLM_TIMEOUT)

        return ResolvedModel(
            alias=alias, model=model, api_base=api_base, timeout=float(timeout)
        )


_registry: Optional[ModelRegistry] = None


def _config_path() -> Path:
    configured = os.getenv("MODELS_CONFIG_PATH")
    if configured:
        return Path(configured)
    return Path(__file__).resolve().parents[2] / "models.yaml"


def get_registry() -> ModelRegistry:
    global _registry
    if _registry is None:
        path = _config_path()
        config: Dict[str, Any] = {}
        if path.is_file():
            loaded = yaml.safe_load(path.read_text(encoding="utf-8"))
            if isinstance(loaded, dict):
                config = loaded
        _registry = ModelRegistry(config)
    return _registry


def reset_registry() -> None:
    """Testing hook: force a reload on next get_registry()."""
    global _registry
    _registry = None
