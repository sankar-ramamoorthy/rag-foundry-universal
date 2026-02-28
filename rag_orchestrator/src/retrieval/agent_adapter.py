# rag_orchestrator/src/retrieval/agent_adapter.py

import logging
from typing import List, Dict, Optional, Callable

from .types import RetrievedContext, RetrievedChunk

logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)  # Can be overridden externally


def prepare_chunks_for_agent(
    retrieved: RetrievedContext,
    *,
    document_order: Optional[List[str]] = None,  # optional explicit document ordering
    max_chunks_per_doc: int = 5,
    max_total_chunks: int = 50,
    max_tokens: Optional[int] = None,  # optional token budget
    chunk_token_count: Optional[Callable[[RetrievedChunk], int]] = None,  # token counting func
    filter_chunk: Optional[Callable[[RetrievedChunk], bool]] = None,  # optional chunk filter
    debug: bool = False,
) -> List[Dict[str, object]]:
    """
    Convert RetrievedContext into a deterministic list of chunk dicts for agent consumption,
    preserving provenance, enforcing optional token budget, scoring, and filtering.

    Args:
        retrieved: RetrievedContext from execute_retrieval_plan.
        document_order: Optional explicit document ordering (seeds first).
        max_chunks_per_doc: Max chunks to take per document.
        max_total_chunks: Max total chunks to return across all documents.
        max_tokens: Optional global token budget.
        chunk_token_count: Function to estimate tokens per chunk.
        filter_chunk: Optional function to filter chunks.
        debug: Enable debug logging.

    Returns:
        List[Dict[str, object]]: Flattened, deterministic chunks with:
            - 'text': chunk text
            - 'document_id': source document
            - 'chunk_id': unique chunk id
            - 'score': chunk score if present
            - 'metadata': chunk metadata dict
    """

    if debug:
        logger.setLevel(logging.DEBUG)

    if document_order is None:
        document_order = sorted(retrieved.chunks_by_document.keys())

    logger.info(
        f"Preparing agent-ready chunks for {len(document_order)} documents "
        f"(max_chunks_per_doc={max_chunks_per_doc}, max_total_chunks={max_total_chunks}, max_tokens={max_tokens})"
    )

    final_chunks: List[Dict[str, object]] = []
    total_tokens = 0

    for doc_id in document_order:
        chunks: List[RetrievedChunk] = retrieved.chunks_by_document.get(doc_id, [])
        if not chunks:
            logger.debug(f"No chunks found for document_id={doc_id}, skipping")
            continue

        # Slice per-document
        selected_chunks = chunks[:max_chunks_per_doc]

        for c in selected_chunks:
            # Optional filtering
            if filter_chunk and not filter_chunk(c):
                logger.debug(f"Chunk {c.chunk_id} filtered out")
                continue

            chunk_dict: Dict[str, object] = {
                "text": c.text,
                "document_id": c.document_id,
                "chunk_id": c.chunk_id,
                "score": getattr(c, "score", None),
                "metadata": c.metadata,
            }

            # Token budget enforcement
            chunk_tokens = chunk_token_count(c) if chunk_token_count else 0
            if max_tokens is not None and total_tokens + chunk_tokens > max_tokens:
                logger.debug(
                    f"Reached max_tokens={max_tokens} after {total_tokens} tokens, stopping"
                )
                return final_chunks  # stop adding more chunks

            final_chunks.append(chunk_dict)
            total_tokens += chunk_tokens

            if len(final_chunks) >= max_total_chunks:
                logger.debug(f"Reached max_total_chunks={max_total_chunks}, stopping")
                return final_chunks

        logger.debug(
            f"Document {doc_id}: {len(selected_chunks)} chunks considered "
            f"(total so far={len(final_chunks)}, tokens={total_tokens})"
        )

    logger.info(f"Prepared {len(final_chunks)} chunks for agent consumption with provenance, total tokens={total_tokens}")
    return final_chunks
