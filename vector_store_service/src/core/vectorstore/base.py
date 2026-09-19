# src/core/vectorstore/base.py
# vector_store_service/src/core/vectorstore/base.py
from abc import ABC, abstractmethod
from typing import Iterable, Sequence, List

# Import from shared
from shared.models.vector import VectorRecord


class VectorStore(ABC):
    @property
    @abstractmethod
    def dimension(self) -> int:
        """Return the dimension of the vectors."""
        ...

    @abstractmethod
    def add(self, records: Iterable[VectorRecord]) -> None:
        """Add a list of VectorRecords to the store."""
        ...

    @abstractmethod
    def similarity_search(
        self,
        query_vector: Sequence[float],
        k: int,
    ) -> List[VectorRecord]:
        """Return the top k most similar vectors."""
        ...

    @abstractmethod
    def delete_by_ingestion_id(self, ingestion_id: str) -> None:
        """Delete all vectors associated with a given ingestion_id."""
        ...

    @abstractmethod
    def retag_ingestion_id(
        self,
        document_ids: List[str],
        new_ingestion_id: str,
        provenance_by_document_id: "dict[str, dict] | None" = None,
    ) -> int:
        """Re-tag every vector row for the given document_ids to
        new_ingestion_id, in place (no re-embedding). Returns the number
        of rows updated. Issue #196 (FR-007b): carries a reused, unchanged
        artifact's existing vectors forward to the new generation.

        Issue #199 (ADR-053, Stage B2 incremental-reuse fix): when
        `provenance_by_document_id` is given, each listed document_id's
        `source_metadata.provenance` key is patched in the same update --
        every other `source_metadata` key is preserved unchanged. This is
        the only way a reused (not re-chunked/re-embedded) artifact's
        vector-level provenance can ever reach the current classifier's
        output; DocumentNode.provenance alone (Stage B1) is not enough,
        since /v1/rag reads chunk-level source_metadata, not the graph.
        A document_id present in `document_ids` but absent from the map
        is retagged only (no provenance change) -- defensive, not the
        expected call shape from ingestion_service.
        """
        ...
