# ingestion_service/src/api/v1/chunks.py
"""
Endpoint to fetch chunk texts for a given ingestion_id.
Used by llm_service/summarize.py to retrieve document content
without performing vector similarity search.

ADR compliance: ingestion_db is owned exclusively by ingestion_service.
No other service queries the DB directly — they call this endpoint instead.
"""
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from typing import List
from uuid import UUID

from src.core import db_utils

router = APIRouter(tags=["chunks"])


class ChunkTextResponse(BaseModel):
    ingestion_id: str
    chunks: List[str]
    count: int


@router.get("/chunks/{ingestion_id}", response_model=ChunkTextResponse)
def get_chunks_by_ingestion(ingestion_id: str) -> ChunkTextResponse:
    """
    Return all chunk texts for a given ingestion_id.
    No vector similarity — pure DB lookup.
    Called by llm_service to fetch content for summarization.
    """
    try:
        uid = UUID(ingestion_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid ingestion_id format")

    chunks = db_utils.get_chunk_texts_by_ingestion_id(str(uid))

    if not chunks:
        raise HTTPException(
            status_code=404,
            detail=f"No chunks found for ingestion_id {ingestion_id}"
        )

    return ChunkTextResponse(
        ingestion_id=ingestion_id,
        chunks=chunks,
        count=len(chunks),
    )