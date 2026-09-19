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
    # Stored ingestion ordinal, distinct from position in a ranked fetch.
    chunk_index: Optional[int] = None
    fetch_position: Optional[int] = None
    # Issue #142 (fix for #141): document_nodes.doc_type (python source /
    # markdown_section / etc.), for the doc-type-aware seed tie-break.
    # None for chunks constructed without it (predates this field).
    doc_type: Optional[str] = None
    # Issue #199 (ADR-053, Stage B2): the ADR-053 provenance envelope,
    # transported from DocumentNode.provenance (Stage B1) through chunk
    # metadata -- read-only passthrough, never used here to rank, filter,
    # or select. None for a pre-B1 row or a chunk predating this field.
    provenance: Optional[dict] = None


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
