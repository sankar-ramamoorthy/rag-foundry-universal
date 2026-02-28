# rag_orchestrator/src/retrieval/vector_store_protocol.py

from typing import List, Protocol
from .types import RetrievedChunk


class VectorStore(Protocol):
    def search_chunks_for_document(
        self,
        *,
        document_id: str,
        top_k: int,
    ) -> List[RetrievedChunk]:
        """
        Return top-k chunks for a single document node.

        Assumptions:
        - Vector similarity handled internally
        - No cross-document leakage
        """
        ...
