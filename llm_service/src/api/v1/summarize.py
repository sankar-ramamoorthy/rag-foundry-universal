# llm-service/src/api/v1/summarize.py - MS7-IS2
import logging
from uuid import UUID
from typing import List
import httpx
from fastapi import APIRouter, HTTPException

from src.core.config import (
    DEFAULT_LLM_PROVIDER,
)
from src.core.llm_client import generate_completion

router = APIRouter(prefix="/v1/summarize", tags=["summaries"])
logging.basicConfig(level=logging.DEBUG)
logger = logging.getLogger(__name__)
logger.setLevel(logging.DEBUG)

INGESTION_SERVICE_URL = "http://ingestion_service:8000"

logger.warning("🔍 summarize.py VERSION: INGESTION_SERVICE_URL build")

async def fetch_chunks(ingestion_id: str) -> List[str]:
    """
    Fetch chunk texts for ingestion_id from ingestion_service.
    ADR compliance: ingestion_db is owned by ingestion_service only.
    No vector search — pure content lookup via HTTP.
    """
    url = f"{INGESTION_SERVICE_URL}/v1/chunks/{ingestion_id}"

    async with httpx.AsyncClient(timeout=30) as client:
        resp = await client.get(url)
        if resp.status_code == 404:
            logger.warning(f"No chunks found for ingestion_id {ingestion_id}")
            return []
        resp.raise_for_status()
        data = resp.json()
        texts = data.get("chunks", [])
        logger.info(f"✅ MS7: Fetched {len(texts)} chunks for {ingestion_id}")
        return texts


async def update_document_summary(ingestion_id: str, summary: str):
    """Update document_nodes.summary via ingestion_service."""
    ingestion_service_url = f"{INGESTION_SERVICE_URL}/v1/summary"
    logger.info(f"summarize.py update_document_summary: {ingestion_service_url}")
    logger.info(f"summarize.py update_document_summary summary: {summary[:100]}")

    async with httpx.AsyncClient(timeout=100) as client:
        resp = await client.post(
            ingestion_service_url,
            json={"ingestion_id": ingestion_id, "summary": summary}
        )
        if resp.status_code not in [200, 201]:
            logger.warning(
                f"⚠️ MS7: Failed to update summary: "
                f"{resp.status_code} url: {ingestion_service_url}"
            )
        else:
            logger.info(f"✅ MS7: Summary saved to DB for {ingestion_id}")


@router.post("/{ingestion_id}")
async def generate_summary(ingestion_id: str):
    """MS7-IS2: Generate LLM summary for document ingestion."""
    try:
        logger.info(f"summarize.py generate_summary: {ingestion_id}")
        UUID(ingestion_id)  # validate format
        logger.info("calling fetch_chunks")

        # 1. Fetch chunks from ingestion_service (not vector store)
        chunk_texts = await fetch_chunks(ingestion_id)
        if not chunk_texts:
            raise HTTPException(status_code=404, detail="No chunks found for ingestion_id")

        # 2. Join top 5 chunks, truncate if needed
        full_text = "\n\n".join(chunk_texts[:5])
        if len(full_text) > 4000:
            full_text = full_text[:4000] + "..."

        # 3. Build prompt
        logger.info("Build prompt")
        context = f"Document chunks for summarization:\n\n{full_text}"
        query = "Summarize this document in 2-3 sentences. Focus on main topics, key entities, and purpose."

        # 4. Call LLM
        logger.info("summarize.py call generate_completion")
        result = await generate_completion(
            context=context,
            query=query,
            provider=DEFAULT_LLM_PROVIDER,
            model="phi4-mini:latest",
        )

        summary = result.get("response", "Summary generation failed")

        # 5. Save summary back to ingestion_service
        logger.info(f"summarize.py saving summary for {ingestion_id}: {summary[:100]}")
        await update_document_summary(ingestion_id, summary)

        logger.info(f"✅ MS7 COMPLETE: {ingestion_id} → {summary[:100]}...")
        return {
            "status": "summary_generated",
            "summary": summary,
            "ingestion_id": ingestion_id,
        }

    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid ingestion_id format")
    except httpx.HTTPStatusError as e:
        logger.error(f"❌ MS7 HTTP error: {e}")
        raise HTTPException(status_code=500, detail=f"Service unavailable: {e}")
    except Exception as e:
        logger.exception(f"❌ MS7 FAILED {ingestion_id}: {e}")
        raise HTTPException(status_code=500, detail=str(e))