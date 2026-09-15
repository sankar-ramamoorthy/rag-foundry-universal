# rag_orchestrator/src/core/reranker.py
"""
Optional cross-encoder reranker (WP-S8 stub, `DOCS/audit/04-Scalability-Plan.md`).

Flag-gated via `Settings.RERANK_ENABLED` (default off) and overridable
per-request (`RAGQuery.rerank` / `SimpleRAGQuery.rerank`) so it can be
A/B compared without a redeploy. This repo's own decision gate
(`DOCS/audit/08-RAG-Quality-Evaluation-Methodology.md` #4) says not to
start reranker work until an evaluation shows correct-but-buried-deep
evidence as the dominant failure mode -- that evaluation hadn't been
re-run post-issue-#150 when this was built; it was built anyway as a
deliberate, informed call (comparing on/off requires having the "on"
side to compare against) rather than a bypass of the gate's intent.
Nothing here changes any default: RERANK_ENABLED stays False until real
A/B evidence says otherwise.

Applies equally to the graph-aware path (`core/service.py`) and the
flat document path (`core/simple_service.py`) -- both funnel their
candidate chunks through the same `List[Dict[str, object]]` shape
(`agent_chunks`, each with a "text" key) before token-budget
truncation, so one `rerank_chunks()` call serves both.
"""
from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional, Protocol

logger = logging.getLogger(__name__)


class CrossEncoderProtocol(Protocol):
    """Minimal shape rerank_chunks() needs -- lets tests inject a fake
    without loading the real (heavy, network-fetched) model."""

    def predict(self, pairs: List[tuple[str, str]]) -> List[float]: ...


_reranker_cache: Dict[str, CrossEncoderProtocol] = {}


def get_reranker(model_name: str) -> CrossEncoderProtocol:
    """Process-wide cached CrossEncoder instance, one per model_name.

    Loading a cross-encoder is expensive (model weights fetched/loaded
    from disk); reusing one instance across requests is essential, the
    same reasoning as caching the embedder in shared/embedders.
    """
    if model_name not in _reranker_cache:
        from sentence_transformers import CrossEncoder  # heavy import, deferred

        logger.info("Loading reranker model %s", model_name)
        _reranker_cache[model_name] = CrossEncoder(model_name)
    return _reranker_cache[model_name]


def reset_reranker_cache() -> None:
    """Testing hook: force a fresh load on next get_reranker() call."""
    global _reranker_cache
    _reranker_cache = {}


def rerank_chunks(
    query: str,
    chunks: List[Dict[str, Any]],
    *,
    top_k: int,
    model_name: str,
    reranker: Optional[CrossEncoderProtocol] = None,
) -> List[Dict[str, Any]]:
    """
    Cross-encoder reranking over an already-retrieved candidate pool.

    Unlike embedding similarity (computed once per chunk, independent of
    the query), a cross-encoder scores the query and candidate text
    jointly -- it can correct cases where embedding similarity ranked a
    near-miss distractor above the real answer, at the cost of one
    forward pass per candidate (not viable at index-scan scale, fine
    over an already-narrowed pool of a few dozen chunks).

    Returns the top_k highest-scoring chunks, most-relevant first, each
    dict otherwise unchanged (callers downstream don't need to know
    reranking happened). When `chunks` is empty, returns it unchanged.
    top_k >= len(chunks) still re-sorts by cross-encoder score rather
    than being a no-op, so the caller gets a consistent relevance order
    either way.
    """
    if not chunks:
        return chunks

    model = reranker or get_reranker(model_name)
    pairs = [(query, str(c.get("text", ""))) for c in chunks]
    scores = model.predict(pairs)

    scored = list(zip(chunks, scores))
    scored.sort(key=lambda pair: pair[1], reverse=True)
    return [c for c, _ in scored[:top_k]]
