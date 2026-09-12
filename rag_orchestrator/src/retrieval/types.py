# rag_orchestrator/src/retrieval/types.py

from dataclasses import dataclass
from typing import Dict, List, Optional


@dataclass(frozen=True)
class RetrievedChunk:
    chunk_id: str
    document_id: str
    text: str
    score: Optional[float]  # can be None if not provided
    metadata: dict
    # WP-T1a: first-class canonical_id instead of ad hoc metadata digging
    # (metadata["canonical_id"] or metadata["source_metadata"]["canonical_id"]).
    canonical_id: Optional[str] = None


@dataclass(frozen=True)
class RetrievedContext:
    """
    Result of executing a RetrievalPlan.

    Guarantees:
    - All chunks belong to documents listed in the plan
    - Grouped by document_id
    - Deterministic ordering
    """
    chunks_by_document: Dict[str, List[RetrievedChunk]]
