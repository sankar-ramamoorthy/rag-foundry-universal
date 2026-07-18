# ingestion_service/src/core/http_vectorstore.py
import requests
from typing import List, Any, Optional
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

    PERSIST_BATCH_SIZE = 500

    def _build_record(
        self,
        chunk: Chunk,
        embedding: Any,
        ingestion_id: str,
        chunk_index: int,
        document_id: Optional[str] = None,
    ) -> dict:
        metadata_dict = dict(chunk.metadata or {})
        metadata_dict["chunk_text"] = chunk.content

        record = {
            "vector": embedding,
            "metadata": {
                "ingestion_id": ingestion_id,
                "chunk_id": chunk.chunk_id,
                "chunk_index": chunk_index,
                "chunk_strategy": chunk.metadata.get("chunk_strategy", "unknown"),
                "chunk_text": chunk.content,
                "source_metadata": metadata_dict,
                "provider": chunk.metadata.get("provider", self.provider),
            },
        }
        # MS6-IS2: Add document_id for new vector_chunks path
        if document_id:
            record["metadata"]["document_id"] = str(document_id)
        return record

    def persist(
        self,
        chunks: List[Chunk],
        embeddings: List[Any],
        ingestion_id: str,
        document_id: Optional[str] = None,  # MS6-IS1: NEW - Link to DocumentNode
    ) -> None:
        """
        Persist chunk embeddings to vector_store_service (vector_chunks table).
        """
        logger.debug("HttpVectorStore persist")
        records = [
            self._build_record(chunk, embedding, ingestion_id, i, document_id)
            for i, (chunk, embedding) in enumerate(zip(chunks, embeddings))
        ]
        self.add_vectors(records)
        logger.info(
            f"Persisted {len(records)} vectors for ingestion {ingestion_id} "
            f"with document_id {document_id}"
        )

    def persist_batch(
        self,
        chunks: List[Chunk],
        embeddings: List[Any],
        ingestion_id: str,
        document_ids: List[str],
        batch_size: Optional[int] = None,
    ) -> None:
        """
        Persist chunks belonging to many documents in one pass (F-08).

        Each chunk carries its own document_id; records are sent to
        /v1/vectors/batch in slices of `batch_size` so HTTP round-trips
        scale with batches, not artifacts. chunk_index restarts per document.
        """
        if len(chunks) != len(document_ids):
            raise ValueError(
                f"persist_batch mismatch: {len(chunks)} chunks, "
                f"{len(document_ids)} document_ids"
            )
        if batch_size is None:
            batch_size = self.PERSIST_BATCH_SIZE

        index_by_doc: dict = {}
        records = []
        for chunk, embedding, document_id in zip(chunks, embeddings, document_ids):
            chunk_index = index_by_doc.get(document_id, 0)
            index_by_doc[document_id] = chunk_index + 1
            records.append(
                self._build_record(
                    chunk, embedding, ingestion_id, chunk_index, document_id
                )
            )

        for start in range(0, len(records), batch_size):
            self.add_vectors(records[start:start + batch_size])

        logger.info(
            f"Persisted {len(records)} vectors for ingestion {ingestion_id} "
            f"across {len(index_by_doc)} documents in "
            f"{-(-len(records) // batch_size) if records else 0} batch(es)"
        )

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
