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
        self, document_ids: List[str], new_ingestion_id: str,
    ) -> int:
        """Re-tag every vector row for the given document_ids to
        new_ingestion_id, in place (no re-embedding). Returns the number
        of rows updated. Issue #196 (FR-007b): carries a reused, unchanged
        artifact's existing vectors forward to the new generation.
        """
        ...
