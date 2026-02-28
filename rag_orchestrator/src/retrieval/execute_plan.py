# rag_orchestrator/src/retrieval/execute_plan.py

from typing import Iterable, Dict, List
import logging

from .types import RetrievedContext, RetrievedChunk
from shared.retrieval.retrieval_plan import RetrievalPlan, ExpansionMetadata

logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)  # Default level, can be overridden externally


def execute_retrieval_plan(
    *,
    plan: RetrievalPlan,
    retrieved_chunks_by_document: Dict[str, List[RetrievedChunk]],
    top_k_per_document: int = 5,
    debug: bool = False,
) -> RetrievedContext:
    """
    Execute a RetrievalPlan using pre-fetched chunks.

    Behavior:
    - Only seed + expanded document IDs are considered
    - Chunks are strictly bounded by the allowed documents
    - No traversal, no expansion, no ranking logic here

    Determinism:
    - Document iteration order is stable
    - Chunk ordering is delegated to upstream retrieval (HTTP results)

    Observability:
    - Logs edges from seed -> expanded documents
    - Logs retrieved chunk counts per document
    - Logs chunk details (ID, score, first 50 chars)
    """

    if debug:
        logger.setLevel(logging.DEBUG)

    total_seed = len(plan.seed_document_ids)
    total_expanded = len(plan.expanded_document_ids)
    logger.info(f"Executing RetrievalPlan: {total_seed} seed docs, {total_expanded} expanded docs")

    # 1️⃣ Compute allowed document IDs (hard boundary)
    allowed_document_ids: List[str] = _ordered_unique(
        list(plan.seed_document_ids) + list(plan.expanded_document_ids)
    )
    logger.debug(f"Allowed document IDs (ordered): {allowed_document_ids}")

    # 2️⃣ Log the expansion metadata edges for observability
    for target_id, meta in plan.expansion_metadata.items():
        logger.debug(
            f"Expanded doc '{target_id}' from source '{meta.source_document_id}' "
            f"via relation '{meta.relation_type}'"
        )

    # 3️⃣ Use pre-fetched chunks per document
    chunks_by_document: Dict[str, List[RetrievedChunk]] = {}

    for document_id in allowed_document_ids:
        chunks = retrieved_chunks_by_document.get(document_id, [])[:top_k_per_document]

        # Safety invariant: no leakage
        for chunk in chunks:
            if chunk.document_id != document_id:
                raise ValueError(
                    f"Retrieved chunk from document {chunk.document_id}, expected {document_id}"
                )

        chunks_by_document[document_id] = chunks

        # 4️⃣ Detailed chunk logging
        for c in chunks:
            preview = (c.text[:50] + "...") if len(c.text) > 50 else c.text
            logger.debug(f"Doc={document_id} | ChunkID={c.chunk_id} | Score={c.score:.4f} | TextPreview='{preview}'")

        logger.debug(f"Retrieved {len(chunks)} chunks for document_id={document_id}")

    logger.info(f"Finished executing RetrievalPlan; total documents retrieved: {len(chunks_by_document)}")
    return RetrievedContext(chunks_by_document=chunks_by_document)


def _ordered_unique(ids: Iterable[str]) -> List[str]:
    """
    Preserve order while removing duplicates.
    Deterministic across runs.
    """
    seen = set()
    result = []
    for _id in ids:
        if _id not in seen:
            seen.add(_id)
            result.append(_id)
    return result
