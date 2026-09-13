# llm_service/src/core/model_catalog.py
"""
WP-M6: dynamic model catalog -- advisory/observational state only.

For each provider family that exposes a "list models" endpoint, fetch the
currently available model IDs, cache them with a TTL, and degrade to the
last-known-good result on any fetch failure. This is convenience,
visibility, and free-tier filtering -- NEVER a gate. `resolve()` in
model_registry.py already accepts a raw LiteLLM string with no catalog
lookup at all, and that stays true: an operator can always use a model
this module has never heard of, doesn't currently list, or is temporarily
failing to fetch. Nothing here is consulted when validating a model_policy
write -- that's `registry.resolve()` alone.

Free-tier detection is deliberately not uniform across providers. Only
OpenRouter exposes real per-model pricing, so only OpenRouter entries ever
get `free=True`/`free=False`; Groq and NVIDIA NIM's model-list responses
carry no equivalent signal, so their entries always get `free=None`
(unknown) rather than a guessed value.
"""
from __future__ import annotations

import logging
import os
import time
from dataclasses import dataclass
from typing import Any, Awaitable, Callable, Dict, List, Optional, Tuple

import httpx

from src.core.config import MODEL_CATALOG_TTL_SECONDS

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class CatalogEntry:
    id: str
    free: Optional[bool] = None


@dataclass
class _CacheEntry:
    models: List[CatalogEntry]
    fetched_at: float


_cache: Dict[str, _CacheEntry] = {}


def reset_catalog_cache() -> None:
    """Testing hook: force a fresh fetch on next get_catalog() call."""
    global _cache
    _cache = {}


async def get_catalog(
    cache_key: str,
    provider: str,
    entry: Dict[str, Any],
    *,
    force: bool = False,
) -> Tuple[List[CatalogEntry], bool, bool]:
    """Returns (models, stale, configured).

    `configured` is False only when the entry names a credential env var
    that isn't set -- in that case the HTTP call is skipped entirely
    (avoids a guaranteed-401 every TTL cycle) and models is always [].
    `stale` is True when a fetch was attempted and failed but a
    previously cached result was returned instead of raising.
    """
    credential_env = entry.get("credential_env")
    if credential_env and not os.getenv(credential_env):
        return [], False, False

    cached = _cache.get(cache_key)
    if (
        cached is not None
        and not force
        and (time.time() - cached.fetched_at) < MODEL_CATALOG_TTL_SECONDS
    ):
        return cached.models, False, True

    fetcher = _FETCHERS.get(provider)
    if fetcher is None:
        return (cached.models if cached else []), bool(cached), True

    try:
        models = await fetcher(entry)
    except Exception as e:  # noqa: BLE001 - any fetch error degrades gracefully
        logger.warning(
            "Model catalog fetch failed for %s (%s): %s", cache_key, provider, e
        )
        if cached is not None:
            return cached.models, True, True
        return [], False, True

    _cache[cache_key] = _CacheEntry(models=models, fetched_at=time.time())
    return models, False, True


def _bearer_headers(entry: Dict[str, Any]) -> Dict[str, str]:
    credential_env = entry.get("credential_env")
    api_key = os.getenv(credential_env) if credential_env else None
    return {"Authorization": f"Bearer {api_key}"} if api_key else {}


async def _fetch_openrouter(entry: Dict[str, Any]) -> List[CatalogEntry]:
    async with httpx.AsyncClient(timeout=10) as client:
        resp = await client.get(entry["catalog_url"], headers=_bearer_headers(entry))
        resp.raise_for_status()
        data = resp.json()

    models = []
    for m in data.get("data", []):
        pricing = m.get("pricing") or {}
        prompt_price = pricing.get("prompt")
        completion_price = pricing.get("completion")
        free: Optional[bool] = None
        if prompt_price is not None and completion_price is not None:
            free = prompt_price == "0" and completion_price == "0"
        models.append(CatalogEntry(id=m["id"], free=free))
    return sorted(models, key=lambda e: e.id)


async def _fetch_openai_compatible(entry: Dict[str, Any]) -> List[CatalogEntry]:
    """Groq and NVIDIA NIM both expose an OpenAI-compatible /models list
    with no pricing/free signal -- every entry gets free=None."""
    async with httpx.AsyncClient(timeout=10) as client:
        resp = await client.get(entry["catalog_url"], headers=_bearer_headers(entry))
        resp.raise_for_status()
        data = resp.json()
    return sorted(
        (CatalogEntry(id=m["id"], free=None) for m in data.get("data", [])),
        key=lambda e: e.id,
    )


async def _fetch_ollama(entry: Dict[str, Any]) -> List[CatalogEntry]:
    async with httpx.AsyncClient(timeout=3) as client:
        resp = await client.get(f"{entry['api_base']}/api/tags")
        resp.raise_for_status()
        data = resp.json()
    return sorted(
        (CatalogEntry(id=m["name"], free=None) for m in data.get("models", [])),
        key=lambda e: e.id,
    )


_FETCHERS: Dict[str, Callable[[Dict[str, Any]], Awaitable[List[CatalogEntry]]]] = {
    "openrouter": _fetch_openrouter,
    "groq": _fetch_openai_compatible,
    "nvidia_nim": _fetch_openai_compatible,
    "ollama": _fetch_ollama,
}
