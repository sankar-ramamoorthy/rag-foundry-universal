# ingestion_service/src/core/http_vectorstore.py
import time

import requests
from typing import List, Any, Optional
import logging

from shared.chunks import Chunk
from src.core.batch_contracts import validate_batch_identity
from src.core.worker_context import check_ownership

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
        *,
        chunk_indices: list[int] | None = None,
    ) -> None:
        """
        Persist chunks belonging to many documents in one pass (F-08).

        Each chunk carries its own document_id; records are sent to
        /v1/vectors/batch in slices of `batch_size` so HTTP round-trips
        scale with batches, not artifacts. Explicit chunk_indices preserve
        document-local ordinals across calls. Legacy callers enumerate locally.
        """
        validate_batch_identity(len(chunks), document_ids, chunk_indices)
        if len(chunks) != len(embeddings):
            raise ValueError(
                f"persist_batch mismatch: {len(chunks)} chunks, "
                f"{len(embeddings)} embeddings"
            )
        if batch_size is None:
            batch_size = self.PERSIST_BATCH_SIZE
        if type(batch_size) is not int or batch_size <= 0:
            raise ValueError("batch_size must be a positive integer")

        index_by_doc: dict = {}
        records = []
        for position, (chunk, embedding, document_id) in enumerate(
            zip(chunks, embeddings, document_ids)
        ):
            chunk_index = (
                chunk_indices[position] if chunk_indices is not None
                else index_by_doc.get(document_id, 0)
            )
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

    # #287: one slow batch must not kill a whole ingestion. Safe only
    # because the store's batch insert is idempotent (ON CONFLICT DO NOTHING).
    MAX_ATTEMPTS = 3
    RETRY_BACKOFF_SECONDS = (5, 15)

    @staticmethod
    def _is_transient(exc: Exception) -> bool:
        if isinstance(exc, (requests.Timeout, requests.ConnectionError)):
            return True
        if isinstance(exc, requests.HTTPError) and exc.response is not None:
            return exc.response.status_code in (502, 503, 504)
        return False

    def add_vectors(self, records: List[dict]):
        """Send a batch of vectors to vector_store_service.

        Transient failures (timeout, connection error, 502/503/504) are
        retried a bounded number of times with backoff; anything else
        fails immediately.
        """
        url = f"{self.base_url}/v1/vectors/batch"
        for attempt in range(1, self.MAX_ATTEMPTS + 1):
            check_ownership()
            try:
                resp = requests.post(url, json={"records": records}, timeout=90)
                resp.raise_for_status()
                return resp.json()
            except requests.RequestException as exc:
                if attempt == self.MAX_ATTEMPTS or not self._is_transient(exc):
                    raise
                delay = self.RETRY_BACKOFF_SECONDS[
                    min(attempt - 1, len(self.RETRY_BACKOFF_SECONDS) - 1)
                ]
                logger.warning(
                    "vector batch attempt %d/%d failed (%s); retrying in %ds",
                    attempt, self.MAX_ATTEMPTS, type(exc).__name__, delay,
                )
                time.sleep(delay)

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
        check_ownership()
        url = f"{self.base_url}/v1/vectors/by-ingestion/{ingestion_id}"
        resp = requests.delete(url,  timeout=90)
        resp.raise_for_status()
        return resp.status_code == 200

    RETAG_BATCH_SIZE = 1000

    def retag_ingestion_id(
        self,
        document_ids: List[str],
        new_ingestion_id: str,
        provenance_by_document_id: "dict[str, dict] | None" = None,
    ) -> int:
        """Re-tag reused artifacts' vectors to the new generation's
        ingestion_id, in place (issue #196, FR-007b) -- no re-embedding.

        Issue #199 (Stage B2 incremental-reuse fix): when
        `provenance_by_document_id` is given, each batch also carries the
        matching document_ids' current provenance, patched into
        `source_metadata.provenance` server-side in the same request --
        the only way a reused artifact's vector-level provenance stays
        current without a re-embed. See
        `vector_store_service`'s `retag_ingestion_id` for the exact
        preserve-other-keys guarantee.
        """
        check_ownership()
        if not document_ids:
            return 0
        provenance_by_document_id = provenance_by_document_id or {}
        url = f"{self.base_url}/v1/vectors/retag"
        total = 0
        for start in range(0, len(document_ids), self.RETAG_BATCH_SIZE):
            batch = document_ids[start:start + self.RETAG_BATCH_SIZE]
            batch_provenance = {
                document_id: provenance_by_document_id[document_id]
                for document_id in batch
                if document_id in provenance_by_document_id
            }
            resp = requests.post(
                url,
                json={
                    "document_ids": batch,
                    "new_ingestion_id": new_ingestion_id,
                    "provenance_by_document_id": batch_provenance or None,
                },
                timeout=90,
            )
            resp.raise_for_status()
            total += resp.json().get("count", 0)
        return total
