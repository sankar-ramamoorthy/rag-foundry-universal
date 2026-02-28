# llm-service/src/api/v1/summarize.py - MS7-IS2
import logging
import os
from uuid import UUID
from typing import List
import httpx
from fastapi import APIRouter, HTTPException, BackgroundTasks

from src.core.config import (
    DEFAULT_LLM_PROVIDER,
    OLLAMA_BASE_URL,
    OLLAMA_MODEL,
)
from src.core.llm_client import generate_completion
router = APIRouter(prefix="/v1/summarize", tags=["summaries"])
logger = logging.getLogger(__name__)
logger.debug(f"summarize.py router: {router}")

# MS7: Reuse vector_store_service + llm_service URLs from ingestion_service pattern
VECTOR_STORE_URL = "http://vector_store_service:8002"
LLM_SERVICE_URL = "http://llm_service:8000"
logger.debug(f"summarize.py LLM_SERVICE_URL: {LLM_SERVICE_URL}")

async def fetch_chunks(ingestion_id: str) -> List[str]:
    """Fetch all chunk_text for ingestion_id from vector-store-service."""
    search_url = f"{VECTOR_STORE_URL}/v1/vectors/search"
    
    # Dummy query vector (we want ALL chunks for this ingestion_id)
    dummy_vector = [0.0] * 768  # nomic-embed-text:v1.5 dimension
    
    payload = {"query_vector": dummy_vector, "k": 1000}
    
    async with httpx.AsyncClient( timeout=90) as client:
        resp = await client.post(search_url, json=payload)
        resp.raise_for_status()
        results = resp.json().get("results", [])
        
        # Filter by ingestion_id + extract texts
        texts = [
            r["text"] 
            for r in results 
            if r.get("metadata", {}).get("ingestion_id") == ingestion_id
        ]
        logger.info(f"✅ MS7: Fetched {len(texts)} chunks for {ingestion_id}")
        return texts

async def update_document_summary(ingestion_id: str, summary: str):
    """Update document_nodes.summary via ingestion-service DB."""
    # MS7-IS3: Direct DB update via ingestion-service (create endpoint later)
    ingestion_service_url = "http://ingestion_service:8000/v1/summary"
    logger.debug(f"summarize.py update_document_summary : {ingestion_service_url}")
    logger.info(f"summarize.py update_document_summary : {ingestion_service_url}")
    logger.info(f"summarize.py update_document_summary summary is : {summary}")
    async with httpx.AsyncClient(timeout=100) as client:
        resp = await client.post(
            ingestion_service_url, 
            json={"ingestion_id": ingestion_id, "summary": summary}
        )
        if resp.status_code not in [200, 201]:
            logger.warning(f"⚠️ MS7: Failed to update summary: \
                           {resp.status_code} ingestion_service_url: {ingestion_service_url}")
        else:
            logger.info(f"✅ MS7: Summary saved to DB for {ingestion_id}")

@router.post("/{ingestion_id}")
async def generate_summary(ingestion_id: str):
    """MS7-IS2: Generate LLM summary for document ingestion."""
    try:
        logger.info("summarize.py  generate_summary")
        # 1. Validate UUID
        UUID(ingestion_id)
        
        # 2. Fetch chunks from vector store
        chunk_texts = await fetch_chunks(ingestion_id)
        if not chunk_texts:
            raise HTTPException(status_code=404, detail="No chunks found for ingestion_id")
        
        # 3. Join chunks (truncate if too long)
        full_text = "\n\n".join(chunk_texts[:5])  # Top 5 chunks max
        if len(full_text) > 4000:
            full_text = full_text[:4000] + "..."
        
        # 4. LLM summarize prompt
        context = f"""Document chunks for summarization:

{full_text}"""
        query = "Summarize this document in 2-3 sentences. Focus on main topics, key entities, and purpose."
        
        # 5. Call existing llm_client.generate_completion()
        logger.info("summarize.py call generate_completion ")
        result = await generate_completion(
            context=context,
            query=query,
            provider=DEFAULT_LLM_PROVIDER,
            model="granite4:350m"  # Match rag-orchestrator
        )
        
        summary = result.get("response", "Summary generation failed")
        
        # 6. Update document_nodes.summary (MS7-IS3)
        logger.info(f"summarize.py call update_document_summary for {ingestion_id} → {summary[:100]}")
        await update_document_summary(ingestion_id, summary)
        
        logger.info(f"✅ MS7 COMPLETE: {ingestion_id} → {summary[:100]}...")
        return {"status": "summary_generated", "summary": summary, "ingestion_id": ingestion_id}
        
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid ingestion_id format")
    except httpx.HTTPStatusError as e:
        logger.error(f"❌ MS7 HTTP error: {e}")
        raise HTTPException(status_code=500, detail=f"Service unavailable: {e}")
    except Exception as e:
        logger.error(f"❌ MS7 FAILED {ingestion_id}: {e}")
        raise HTTPException(status_code=500, detail=str(e))
