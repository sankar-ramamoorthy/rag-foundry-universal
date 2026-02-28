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
from src.core.llm_client import generate_completion

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
    except Exception as e:
        logging.exception("Error in /generate")
        return JSONResponse(status_code=500, content={"error": str(e)})

@app.get("/health")
def health_check() -> dict:
    return {
        "status": "ok",
        "default_provider": DEFAULT_LLM_PROVIDER,
        "ollama_model": OLLAMA_MODEL,
    }
