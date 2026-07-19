# llm-service/src/api/v1/main.py - MS7-IS2 FIXED
import logging
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

@app.get("/v1/models")
def list_models() -> dict:
    """WP-M5: the model menu — aliases from models.yaml + the default."""
    return {"models": get_registry().describe(), "default": DEFAULT_ALIAS}


@app.get("/health")
def health_check() -> dict:
    return {
        "status": "ok",
        "default_provider": DEFAULT_LLM_PROVIDER,
        "ollama_model": OLLAMA_MODEL,
    }
