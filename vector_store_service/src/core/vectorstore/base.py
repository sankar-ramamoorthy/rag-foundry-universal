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
