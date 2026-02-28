# vector_store_service/src/api/v1/vectors.py
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from typing import List, Dict, Any, Optional
import logging

from src.core.vectorstore.pgvector_store import PgVectorStore
from src.core.config import get_vector_store
from shared.models.vector import VectorRecord, VectorMetadata

router = APIRouter(prefix="/v1/vectors", tags=["vectors"])
logger = logging.getLogger(__name__)

class VectorMetadataAPI(BaseModel):
    ingestion_id: str
    chunk_id: str
    chunk_index: int
    chunk_strategy: str
    chunk_text: str
    source_metadata: Optional[Dict[str, Any]] = {}
    provider: str = "mock"
    document_id: Optional[str] = None  # MS6-IS3: NEW

class VectorRecordAPI(BaseModel):
    vector: List[float]
    metadata: VectorMetadataAPI

class VectorBatchRequest(BaseModel):
    records: List[VectorRecordAPI]

class VectorSearchRequest(BaseModel):
    query_vector: List[float]
    k: int = 5
    metadata_filter: Optional[Dict[str, Any]] = None  # ADD THIS

class VectorSearchByDocRequest(BaseModel):
    document_id: str
    k: int = 3

@router.post("/batch")
async def add_vectors(
    batch: VectorBatchRequest, store: PgVectorStore = Depends(get_vector_store)
):
    """Add a batch of vectors to the store."""
    try:
        domain_records = []
        for api_record in batch.records:
            metadata = VectorMetadata(
                ingestion_id=api_record.metadata.ingestion_id,
                chunk_id=api_record.metadata.chunk_id,
                chunk_index=api_record.metadata.chunk_index,
                chunk_strategy=api_record.metadata.chunk_strategy,
                chunk_text=api_record.metadata.chunk_text,
                source_metadata=api_record.metadata.source_metadata,
                provider=api_record.metadata.provider,
                document_id=api_record.metadata.document_id,  # MS6-IS3: Pass through
            )
            domain_records.append(
                VectorRecord(vector=api_record.vector, metadata=metadata)
            )

        store.add(domain_records)
        logger.info(f"Added {len(domain_records)} vectors to store")
        return {"status": "ok", "count": len(domain_records)}
    except Exception as e:
        logger.error(f"Error adding vectors: {e}")
        raise HTTPException(status_code=500, detail=str(e))

# ... rest of file unchanged (search, delete endpoints)


@router.post("/search")
async def similarity_search(
    request: VectorSearchRequest, store: PgVectorStore = Depends(get_vector_store)
):
    """Search for similar vectors - MS6 RAG compatible."""
    try:
        logger.debug("similarity_search Search for similar vectors - MS6 RAG compatible")
        results = store.similarity_search(request.query_vector, request.k,
        metadata_filter=request.metadata_filter  )

        # MS6 RAG FIX: Match exact fields expected by rag-orchestrator
        return {
            "results": [
                {
                    "chunk_id": r.metadata.chunk_id,
                    "text": r.metadata.chunk_text,           #  TOP-LEVEL text
                    "document_id": r.metadata.document_id,   #  TOP-LEVEL document_id
                    "score": 0.1,                            #  Add dummy score
                    "metadata": {
                        "ingestion_id": r.metadata.ingestion_id,
                        "chunk_index": r.metadata.chunk_index,
                        "chunk_strategy": r.metadata.chunk_strategy,
                        "source_metadata": r.metadata.source_metadata,
                        "provider": r.metadata.provider,
                    },
                }
                for r in results
            ]
        }
    except Exception as e:
        logger.error(f"Error searching vectors: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.delete("/by-ingestion/{ingestion_id}")
async def delete_by_ingestion(
    ingestion_id: str, store: PgVectorStore = Depends(get_vector_store)
):
    """Delete all vectors for a given ingestion_id."""
    try:
        store.delete_by_ingestion_id(ingestion_id)
        logger.info(f"Deleted vectors for ingestion_id: {ingestion_id}")
        return {"status": "deleted", "ingestion_id": ingestion_id}
    except Exception as e:
        logger.error(f"Error deleting vectors: {e}")
        raise HTTPException(status_code=500, detail=str(e))



@router.post("/search-by-doc")
async def search_by_document(
    request: VectorSearchByDocRequest,
    store: PgVectorStore = Depends(get_vector_store)
):
    """Return chunks for a specific document_id — used for graph expansion."""
    try:
        results = store.get_chunks_by_document_id(request.document_id, request.k)
        return {
            "results": [
                {
                    "chunk_id": r.metadata.chunk_id,
                    "text": r.metadata.chunk_text,
                    "document_id": r.metadata.document_id,
                    "score": 1.0,
                    "metadata": {
                        "ingestion_id": r.metadata.ingestion_id,
                        "chunk_index": r.metadata.chunk_index,
                        "chunk_strategy": r.metadata.chunk_strategy,
                        "source_metadata": r.metadata.source_metadata,
                        "provider": r.metadata.provider,
                    },
                }
                for r in results
            ]
        }
    except Exception as e:
        logger.error(f"Error fetching chunks by document_id: {e}")
        raise HTTPException(status_code=500, detail=str(e))