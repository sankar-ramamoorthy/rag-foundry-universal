# api.py

import logging

import httpx

from src.api.v1.models import RAGQuery, RAGResponse, SimpleRAGQuery,SimpleRAGResponse
from src.core.config import get_settings
from src.core.service import run_rag#, search_documents
from fastapi import APIRouter, HTTPException
from src.core.simple_service import run_simple_rag  # new - no graph
router = APIRouter()

# Set up logging configuration
logging.basicConfig(level=logging.WARNING)
logger = logging.getLogger(__name__)


# /search endpoint to get vector search results without invoking the LLM
#@router.post("/search")
#async def search_endpoint(query: SearchQuery):
#    logger.debug(f"Received search query: {query}")
#
#    try:
#        # Get search results from the service layer
#        results = await search_documents(query.question, query.top_k)
#        return {"results": results}

#    except Exception as e:
#        logger.error(f"Error occurred while searching: {e}")
#        raise HTTPException(
#            status_code=500, detail="An error occurred during the search."
#        )


# /rag endpoint to run the full RAG (retrieval-augmented generation) process
@router.post("/rag", response_model=RAGResponse)
async def rag_endpoint(rag_query: RAGQuery):
    logger.debug(f"Received RAG query: {rag_query}")

    try:
        result = await run_rag(
        query=rag_query.query,
        repo_id=rag_query.repo_id,
        top_k=rag_query.top_k,
        provider=rag_query.provider,
        model=rag_query.model,
        language=rag_query.language,
        rerank=rag_query.rerank,
        )
        return result

    except HTTPException:
        # Preserve service-layer status codes (e.g. 404 unknown repo_id)
        raise
    except Exception as e:
        logger.error(f"Error occurred during the RAG process: {e}")
        raise HTTPException(
            status_code=500,
            detail="An error occurred while processing the RAG request.",
        )


@router.get("/models")
async def list_models():
    """WP-M5: pass through the llm_service model menu so the UI can
    build its dropdown without reaching llm_service directly."""
    settings = get_settings()
    try:
        async with httpx.AsyncClient(timeout=30) as client:
            resp = await client.get(f"{settings.LLM_SERVICE_URL}/v1/models")
            resp.raise_for_status()
            return resp.json()
    except Exception as e:
        logger.error(f"Failed to fetch model menu: {e}")
        raise HTTPException(502, "llm_service model menu unavailable")


@router.get("/repos/{repo_id}/orient")
async def get_repo_orient(repo_id: str):
    """Issue #216: thin passthrough to ingestion_service's deterministic
    ORIENT endpoint (issue #197) -- no vector search, no graph expansion,
    no LLM call, entirely outside run_rag()'s retrieval path. Unlike
    /models above, this preserves ingestion_service's own 404 (no
    completed generation) and 409 (generation predates ORIENT) rather
    than collapsing every failure into one generic status: a caller
    needs to tell "this repo has no ORIENT data" apart from "ingestion_
    service is unreachable" to act correctly (e.g. re-ingest vs. retry).
    """
    settings = get_settings()
    url = f"{settings.INGESTION_SERVICE_URL}/v1/repos/{repo_id}/orient"
    try:
        async with httpx.AsyncClient(timeout=30) as client:
            resp = await client.get(url)
    except httpx.HTTPError as exc:
        logger.error(f"Failed to reach ingestion_service for ORIENT: {exc}")
        raise HTTPException(502, "ingestion_service unavailable") from exc

    if resp.status_code == 200:
        return resp.json()
    if resp.status_code in (404, 409):
        try:
            detail = resp.json().get("detail", resp.text)
        except ValueError:
            detail = resp.text
        raise HTTPException(resp.status_code, detail)
    logger.error(
        f"ingestion_service returned unexpected status {resp.status_code} "
        f"for ORIENT (repo_id={repo_id[:8]})"
    )
    raise HTTPException(502, "ingestion_service returned an unexpected error")


@router.post("/rag/simple", response_model=SimpleRAGResponse)
async def simple_rag_endpoint(simple_rag_query: SimpleRAGQuery):
    """Simple RAG for regular documents - no graph traversal."""
    logger.debug(f"Received RAG query: {simple_rag_query}")

    try:
        result = await run_simple_rag(
        query=simple_rag_query.query,
        top_k=simple_rag_query.top_k,
        provider=simple_rag_query.provider,
        model=simple_rag_query.model,
        rerank=simple_rag_query.rerank,
        )
        return result

    except Exception as e:
        logger.error(f"Error occurred during the RAG process: {e}")
        raise HTTPException(
            status_code=500,
            detail="An error occurred while processing the RAG request.",
        )
