# rag_orchestrator/src/retrieval/agent_adapter.py

import logging
import hashlib
from dataclasses import dataclass
from typing import List, Dict, Optional, Callable

from .types import RetrievedContext, RetrievedChunk

logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)  # Can be overridden externally


def _source_label(c: Dict[str, object]) -> Optional[object]:
    """
    Prefers canonical_id from chunk metadata (`path` or
    `path#Class.method` per ADR-031), then relative_path, then the raw
    document_id. The vector store's search response nests the ingestion
    metadata under `metadata.source_metadata` (vectors.py), so both the
    flat and nested shapes are checked — same duality
    extract_canonical_ids_from_chunks handles.
    """
    raw_metadata = c.get("metadata")
    metadata: Dict[str, object] = (
        raw_metadata if isinstance(raw_metadata, dict) else {}
    )
    raw_nested = metadata.get("source_metadata")
    nested: Dict[str, object] = (
        raw_nested if isinstance(raw_nested, dict) else {}
    )
    return (
        metadata.get("canonical_id")
        or nested.get("canonical_id")
        or metadata.get("relative_path")
        or nested.get("relative_path")
        or c.get("document_id")
    )


def build_sources(agent_chunks: List[Dict[str, object]]) -> List[str]:
    """
    Human-readable, deduplicated source labels (issue #30 Part 4).

    Labels keep first-seen order, so with seeds ordered before expanded
    documents the seed sources come first.
    """
    sources: List[str] = []
    seen: set = set()
    for c in agent_chunks:
        label = _source_label(c)
        if label and label not in seen:
            seen.add(label)
            sources.append(str(label))
    return sources


def conservative_token_count(text: str) -> int:
    """UTF-8 bytes: conservative accounting, not a model tokenizer measurement."""
    return len(text.encode("utf-8"))


def _render_chunk(chunk: Dict[str, object]) -> str:
    label = _source_label(chunk)
    text = str(chunk["text"])
    return f"[Source: {label}]\n{text}" if label else text


@dataclass(frozen=True)
class AssembledContext:
    text: str
    chunks: List[Dict[str, object]]
    token_count: int


def assemble_context(
    agent_chunks: List[Dict[str, object]], max_total_tokens: int
) -> AssembledContext:
    """Select whole passages once, counting labels and separators as well.

    Skip an oversized passage so it cannot suppress later usable evidence.
    The budget is for context only; the caller reserves prompt/output space.
    """
    parts: List[str] = []
    selected: List[Dict[str, object]] = []
    used = 0
    for chunk in agent_chunks:
        part = _render_chunk(chunk)
        cost = conservative_token_count(part) + (2 if parts else 0)
        if used + cost > max_total_tokens:
            continue
        parts.append(part)
        selected.append(chunk)
        used += cost
    return AssembledContext("\n\n".join(parts), selected, used)


def select_chunks_within_token_budget(
    agent_chunks: List[Dict[str, object]], max_total_tokens: int
) -> List[Dict[str, object]]:
    """Compatibility wrapper around the single context selection pass."""
    return assemble_context(agent_chunks, max_total_tokens).chunks


def build_final_context_manifest(
    chunks_in_final_context: List[Dict[str, object]],
    *,
    seed_document_ids: Optional[set] = None,
    expansion_metadata: Optional[Dict[str, object]] = None,
) -> List[Dict[str, object]]:
    """
    WP-T1d: one structured record per chunk that actually crosses into
    the assembled LLM context (survives build_labeled_context's token
    budget) -- the hard boundary the WP-T1 planning doc calls "retrieval
    succeeded only if the needed evidence crossed this boundary".
    Deliberately built from the same chunk list build_labeled_context
    joins (via select_chunks_within_token_budget), so the manifest can
    never drift from what the model actually receives.

    `seed_document_ids`/`expansion_metadata` (plain dicts, matching
    retrieval_plan_dict's shape) are optional so this stays usable
    standalone; without them every chunk's selection_reason is "unknown".
    """
    seed_document_ids = seed_document_ids or set()
    expansion_metadata = expansion_metadata or {}
    manifest: List[Dict[str, object]] = []
    for c in chunks_in_final_context:
        text = str(c.get("text", ""))
        document_id = c.get("document_id")
        meta = expansion_metadata.get(str(document_id)) if document_id else None
        if document_id in seed_document_ids:
            selection_reason = "seed"
        elif isinstance(meta, dict):
            selection_reason = (
                f"expanded via {meta['relation_type']} "
                f"from {meta['source_document_id']}"
            )
        elif document_id is not None:
            selection_reason = "expanded"
        else:
            selection_reason = "unknown"
        manifest.append(
            {
                "canonical_id": c.get("canonical_id"),
                "document_id": document_id,
                "chunk_id": c.get("chunk_id"),
                "chunk_index": c.get("chunk_index"),
                "source_label": _source_label(c),
                "char_count": len(text),
                "text_sha256": hashlib.sha256(text.encode("utf-8")).hexdigest(),
                "token_count": conservative_token_count(_render_chunk(c)),
                "token_count_method": "utf8_bytes_upper_estimate",
                "fetch_position": c.get("fetch_position"),
                "selection_reason": selection_reason,
            }
        )
    return manifest


def build_labeled_context(
    agent_chunks: List[Dict[str, object]], max_total_tokens: int
) -> "tuple[str, int]":
    """
    Join chunk text into the LLM context, each block prefixed with its
    source label so chunks that share surface phrasing (e.g. two
    "p95 latency" figures) but describe different referents stay
    distinguishable to the model instead of blending into one
    undifferentiated wall of text (WP-Q0 Q7 finding, issue tracked
    separately from #64/#65's retrieval-side fixes).
    """
    assembled = assemble_context(agent_chunks, max_total_tokens)
    return assembled.text, assembled.token_count


def prepare_chunks_for_agent(
    retrieved: RetrievedContext,
    *,
    document_order: Optional[List[str]] = None,  # optional explicit document ordering
    max_chunks_per_doc: int = 5,
    max_total_chunks: int = 50,
    max_tokens: Optional[int] = None,  # optional token budget
    chunk_token_count: Optional[
        Callable[[RetrievedChunk], int]
    ] = None,  # token counting func
    filter_chunk: Optional[
        Callable[[RetrievedChunk], bool]
    ] = None,  # optional chunk filter
    debug: bool = False,
) -> List[Dict[str, object]]:
    """
    Convert RetrievedContext into a deterministic list of chunk
    dicts for agent consumption,
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
        f"(max_chunks_per_doc={max_chunks_per_doc}, "
        f"max_total_chunks={max_total_chunks}, max_tokens={max_tokens})"
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
                # WP-T1c: which chunk index (within its document's fetch)
                # this is, for chunk-index-level evidence tracing.
                "chunk_index": getattr(c, "chunk_index", None),
                "fetch_position": getattr(c, "fetch_position", None),
                # WP-T1d: first-class canonical_id, for the final-context
                # manifest (previously only reachable via metadata digging).
                "canonical_id": getattr(c, "canonical_id", None),
            }

            # Token budget enforcement
            chunk_tokens = chunk_token_count(c) if chunk_token_count else 0
            if max_tokens is not None and total_tokens + chunk_tokens > max_tokens:
                logger.debug(
                    f"Reached max_tokens={max_tokens} "
                    f"after {total_tokens} tokens, stopping"
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

    logger.info(
        f"Prepared {len(final_chunks)} chunks for agent consumption "
        f"with provenance, total tokens={total_tokens}"
    )
    return final_chunks
