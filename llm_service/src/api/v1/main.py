# llm-service/src/api/v1/main.py - MS7-IS2 FIXED
import asyncio
import logging

from fastapi import FastAPI, Query
from fastapi.responses import JSONResponse

from src.api.v1.models import GenerateRequest
from src.api.v1 import summarize  # 🔥 MS7-IS2: Import summarize module
from src.core.config import (
    DEFAULT_LLM_PROVIDER,
    OLLAMA_MODEL,
)
from src.core import model_catalog
from src.core.llm_client import AllProvidersFailedError, generate_completion
from src.core.model_registry import (
    DEFAULT_ALIAS,
    UnknownModelAliasError,
    get_registry,
)

app = FastAPI(title="LLM Service")

# 🔥 MS7-IS2: Add summarize router FIRST (prefix=/v1/summarize)
app.include_router(summarize.router)

@app.post("/generate")
async def generate(
    request: GenerateRequest,
    provider: str | None = Query(None),
    model: str | None = Query(None),
) -> dict:
    try:
        return await generate_completion(
            context=request.context,
            query=request.query,
            provider=provider,
            model=model,
        )
    except UnknownModelAliasError as e:
        # WP-M1: unknown alias is a client error, with the valid menu
        return JSONResponse(
            status_code=400,
            content={"error": str(e), "valid_aliases": e.valid_aliases},
        )
    except ValueError as e:
        return JSONResponse(status_code=400, content={"error": str(e)})
    except AllProvidersFailedError as e:
        # WP-M2: actionable outage message, not a stack trace
        logging.error("All LLM providers failed: %s", e)
        return JSONResponse(
            status_code=503,
            content={"error": str(e), "attempted_models": e.attempted},
        )
    except Exception as e:
        logging.exception("Error in /generate")
        return JSONResponse(status_code=500, content={"error": str(e)})

async def _endpoint_inventory(endpoint: dict) -> dict:
    """issue #43: enrich a named endpoint with its live model list so
    the UI can offer `<endpoint>/<model>` choices. Best-effort — an
    unreachable endpoint reports available_models: null and the menu
    still renders. WP-M6: now goes through the shared TTL-cached catalog
    (model_catalog.py) instead of probing /api/tags on every request."""
    entry = dict(endpoint)
    entry["available_models"] = None
    if entry.get("provider") != "ollama":
        return entry
    models, _stale, _configured = await model_catalog.get_catalog(
        entry["name"], "ollama", entry
    )
    if models:
        entry["available_models"] = [m.id for m in models]
    return entry


async def _provider_inventory(provider: dict, *, free_only: bool) -> dict:
    """WP-M6: enrich a provider family with its discovered model catalog.
    Advisory/observational only — never a gate on what /generate accepts.
    An unconfigured or unreachable provider still renders in the menu
    (catalog: [] / null-flagged fields), it just has nothing to show."""
    models, stale, configured = await model_catalog.get_catalog(
        provider["name"], provider["name"], provider
    )
    if free_only:
        models = [m for m in models if m.free is True]
    return {
        "name": provider["name"],
        "configured": configured,
        "catalog": [{"id": m.id, "free": m.free} for m in models],
        "catalog_stale": stale,
    }


@app.get("/v1/models")
async def list_models(free_only: bool = Query(False)) -> dict:
    """WP-M5 + issue #43 + WP-M6: aliases from models.yaml, the default,
    named endpoints with live model inventories, and each provider
    family's dynamically discovered model catalog (advisory only —
    `?free_only=true` filters each provider's catalog to models the
    provider's own pricing data marks as free; it never affects `models`/
    `endpoints`, which have no reliable per-request cost signal)."""
    registry = get_registry()
    endpoints, providers = await asyncio.gather(
        asyncio.gather(
            *(_endpoint_inventory(e) for e in registry.describe_endpoints())
        ),
        asyncio.gather(
            *(
                _provider_inventory(p, free_only=free_only)
                for p in registry.describe_providers()
            )
        ),
    )
    return {
        "models": registry.describe(),
        "default": DEFAULT_ALIAS,
        "endpoints": list(endpoints),
        "providers": list(providers),
    }


@app.get("/health")
def health_check() -> dict:
    return {
        "status": "ok",
        "default_provider": DEFAULT_LLM_PROVIDER,
        "ollama_model": OLLAMA_MODEL,
    }
