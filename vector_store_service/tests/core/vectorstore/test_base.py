"""
Unit tests for the VectorStore abstract base class.

These tests document and enforce the contract that all vector store
implementations must follow. The goal is not to test any concrete
storage behavior, but to ensure interface correctness and clarity.
"""

import pytest

from src.core.vectorstore.base import VectorStore
from shared.models.vector import VectorRecord, VectorMetadata

pytestmark = pytest.mark.unit
def test_vectorstore_is_abstract():
    """
    VectorStore is an abstract base class and must not be instantiable
    without implementing all required abstract methods.
    """
    with pytest.raises(TypeError):
        VectorStore()  # type: ignore[abstract]


def test_vectorstore_requires_all_abstract_methods():
    """
    Any subclass of VectorStore must implement all abstract methods.
    Missing even a single required method should prevent instantiation.
    """

    class IncompleteVectorStore(VectorStore):
        @property
        def dimension(self) -> int:
            return 3

        # Missing add(), similarity_search(), delete_by_ingestion_id()

    with pytest.raises(TypeError):
        IncompleteVectorStore()


def test_vectorstore_contract_with_minimal_implementation():
    """
    A minimal concrete implementation of VectorStore that satisfies
    the abstract contract should be instantiable and callable.

    This test serves as executable documentation of the required
    interface for all vector store implementations.
    """

    class DummyVectorStore(VectorStore):
        def __init__(self):
            self._records = []

        @property
        def dimension(self) -> int:
            return 3

        def add(self, records):
            self._records.extend(records)

        def similarity_search(self, query_vector, k):
            return self._records[:k]

        def delete_by_ingestion_id(self, ingestion_id: str) -> None:
            self._records = [
                r for r in self._records
                if r.metadata.ingestion_id != ingestion_id
            ]

    store = DummyVectorStore()

    metadata = VectorMetadata(
        ingestion_id="ing-1",
        chunk_id="chunk-1",
        chunk_index=0,
        chunk_strategy="test",
        chunk_text="hello world",
        source_metadata={},
        provider="mock",
    )

    record = VectorRecord(vector=[0.1, 0.2, 0.3], metadata=metadata)

    store.add([record])

    results = store.similarity_search([0.1, 0.2, 0.3], k=1)

    assert len(results) == 1
    assert results[0] is record
