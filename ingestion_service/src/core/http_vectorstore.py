# ingestion_service/src/core/http_vectorstore.py
import requests
from typing import List, Any
import logging

from shared.chunks import Chunk

logger = logging.getLogger(__name__)

class HttpVectorStore:
    def __init__(self, base_url: str, provider: str = "ollama"):
        """
        :param base_url: Base URL of vector_store_service API
        :param provider: Embedding provider name
        """
        self.base_url = base_url.rstrip("/")
        self.provider = provider
        logger.debug("ttpVectorStore init")

    def persist(
        self, 
        chunks: List[Chunk], 
        embeddings: List[Any], 
        ingestion_id: str,
        document_id: str = None,  # MS6-IS1: NEW - Link to DocumentNode
    ) -> None:
        """
        Dual-write: legacy vectors + new vector_chunks (MS6).
        """
        logger.debug("HttpVectorStore persist")
        records = []
        for i, (chunk, embedding) in enumerate(zip(chunks, embeddings)):
            metadata_dict = dict(chunk.metadata or {})
            metadata_dict["chunk_text"] = chunk.content

            # Create the record
            record = {
                "vector": embedding,
                "metadata": {
                    "ingestion_id": ingestion_id,
                    "chunk_id": chunk.chunk_id,
                    "chunk_index": i,
                    "chunk_strategy": chunk.metadata.get("chunk_strategy", "unknown"),
                    "chunk_text": chunk.content,
                    "source_metadata": metadata_dict,
                    "provider": chunk.metadata.get("provider", self.provider),
                },
            }
            logger.debug("HttpVectorStore persist document_id check")
            # MS6-IS2: Add document_id for new vector_chunks path
            if document_id:
                logger.debug("HttpVectorStore persist document_id exists")
                record["metadata"]["document_id"] = str(document_id)
            
            records.append(record)

        # Dual-write to vector_store_service (handles both tables internally)
        self.add_vectors(records)
        logger.info(f"Persisted {len(records)} vectors for ingestion {ingestion_id}  with document_id  {document_id}")

    def add_vectors(self, records: List[dict]):
        """Send a batch of vectors to vector_store_service."""
        url = f"{self.base_url}/v1/vectors/batch"
        resp = requests.post(url, json={"records": records},  timeout=90)
        resp.raise_for_status()
        return resp.json()

    def similarity_search(self, query_vector: List[float], k: int = 5):
        """Search the vector store for top-k similar vectors."""
        url = f"{self.base_url}/v1/vectors/search"
        resp = requests.post(
            url, json={"query_vector": query_vector, "k": k},  timeout=90
        )
        resp.raise_for_status()
        return resp.json()

    def delete_by_ingestion_id(self, ingestion_id: str):
        """Delete all vectors for an ingestion_id."""
        url = f"{self.base_url}/v1/vectors/by-ingestion/{ingestion_id}"
        resp = requests.delete(url,  timeout=90)
        resp.raise_for_status()
        return resp.status_code == 200
