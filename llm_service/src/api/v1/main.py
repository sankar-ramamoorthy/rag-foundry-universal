# llm-service/src/api/v1/main.py - MS7-IS2 FIXED
import asyncio
import logging

import httpx
from fastapi import FastAPI, Query
from fastapi.responses import JSONResponse

from src.api.v1.models import GenerateRequest
from src.api.v1 import summarize  # 🔥 MS7-IS2: Import summarize module
from src.core.config import (
    DEFAULT_LLM_PROVIDER,
    OLLAMA_MODEL,
)
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
    still renders."""
    entry = dict(endpoint)
    entry["available_models"] = None
    if entry.get("provider") != "ollama":
        return entry
    try:
        async with httpx.AsyncClient(timeout=3) as client:
            resp = await client.get(f"{entry['api_base']}/api/tags")
            resp.raise_for_status()
            entry["available_models"] = sorted(
                m["name"] for m in resp.json().get("models", [])
            )
    except Exception as e:
        logging.debug("Endpoint %s inventory failed: %s", entry["name"], e)
    return entry


@app.get("/v1/models")
async def list_models() -> dict:
    """WP-M5 + issue #43: aliases from models.yaml, the default, and
    named endpoints with live model inventories."""
    registry = get_registry()
    endpoints = await asyncio.gather(
        *(_endpoint_inventory(e) for e in registry.describe_endpoints())
    )
    return {
        "models": registry.describe(),
        "default": DEFAULT_ALIAS,
        "endpoints": list(endpoints),
    }


@app.get("/health")
def health_check() -> dict:
    return {
        "status": "ok",
        "default_provider": DEFAULT_LLM_PROVIDER,
        "ollama_model": OLLAMA_MODEL,
    }
