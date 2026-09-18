# rag_orchestrator/tests/test_doc_type_tie_break.py
"""
Issue #142 (fix for #141): a self-ingested Markdown evaluation document
outranked the real source code it discussed, because its near-verbatim
question text produced an artificially strong vector-similarity score,
and:
  1. the real answer was excluded from the seed vector search's own
     top_k-bounded result set entirely (confirmed live -- not merely
     outranked within an already-fetched set), and
  2. nothing consulted document_nodes.doc_type as a ranking signal even
     when both candidates were present.

This tests both halves: `_apply_doc_type_tie_break` (the selection
algorithm, in isolation) and hybrid_retrieve's seed-search k widening
(via the same MockTransport payload-capturing pattern as
test_repo_scoping.py).
"""
import asyncio
import json

import httpx
import pytest

from src.core.config import reset_settings_cache
from src.core.service import _apply_doc_type_tie_break, hybrid_retrieve
from rag_orchestrator.src.retrieval.types import RetrievedChunk

pytestmark = pytest.mark.unit

IMPLEMENTATION_DOC_TYPES = frozenset({"python source", "rust source"})


def _chunk(chunk_id: str, score: float, doc_type: str) -> RetrievedChunk:
    return RetrievedChunk(
        chunk_id=chunk_id,
        document_id=f"doc-{chunk_id}",
        text=f"text-{chunk_id}",
        score=score,
        metadata={},
        canonical_id=f"cid-{chunk_id}",
        doc_type=doc_type,
    )


# ------------------------------------------------------------------
# _apply_doc_type_tie_break: pure algorithm
# ------------------------------------------------------------------

def test_promotes_implementation_chunk_within_epsilon_band():
    """Issue #141's exact shape: a markdown chunk narrowly outscores the
    real implementation chunk. Within the epsilon band, implementation
    wins."""
    eval_doc = _chunk("eval", score=0.90, doc_type="markdown_section")
    real_code = _chunk("code", score=0.88, doc_type="python source")
    chunks = [eval_doc, real_code]  # already score-sorted, as vector search returns

    selected = _apply_doc_type_tie_break(
        chunks, top_k=1, epsilon=0.03, implementation_doc_types=IMPLEMENTATION_DOC_TYPES
    )

    assert selected == [real_code]


def test_does_not_override_a_clear_margin():
    """A documentation chunk that is unambiguously the best match (score
    margin exceeds epsilon) must NOT be displaced -- the control case
    proving this isn't a blanket doc_type preference."""
    clearly_best_doc = _chunk("doc", score=0.95, doc_type="markdown_section")
    weaker_code = _chunk("code", score=0.50, doc_type="python source")
    chunks = [clearly_best_doc, weaker_code]

    selected = _apply_doc_type_tie_break(
        chunks, top_k=1, epsilon=0.03, implementation_doc_types=IMPLEMENTATION_DOC_TYPES
    )

    assert selected == [clearly_best_doc]


def test_noop_when_pool_not_wider_than_top_k():
    """When there's nothing beyond the cut line (pool size == top_k, the
    flag-off shape), selection must leave order/content untouched --
    the widened pool is what makes promotion possible at all."""
    chunks = [
        _chunk("a", score=0.9, doc_type="markdown_section"),
        _chunk("b", score=0.8, doc_type="python source"),
    ]

    selected = _apply_doc_type_tie_break(
        chunks, top_k=2, epsilon=0.03, implementation_doc_types=IMPLEMENTATION_DOC_TYPES
    )

    assert selected == chunks


def test_no_promotion_needed_when_best_is_already_implementation():
    """Nothing to do when the top-scored candidate is already an
    implementation doc_type."""
    real_code = _chunk("code", score=0.9, doc_type="python source")
    eval_doc = _chunk("eval", score=0.88, doc_type="markdown_section")
    chunks = [real_code, eval_doc]

    selected = _apply_doc_type_tie_break(
        chunks, top_k=1, epsilon=0.03, implementation_doc_types=IMPLEMENTATION_DOC_TYPES
    )

    assert selected == [real_code]


def test_selects_top_k_from_wider_pool_in_score_order_otherwise():
    """With no doc_type conflict, selection is just top_k by score --
    the existing, unchanged behavior once no tie-break condition fires."""
    chunks = [
        _chunk("a", score=0.9, doc_type="python source"),
        _chunk("b", score=0.7, doc_type="python source"),
        _chunk("c", score=0.5, doc_type="python source"),
    ]

    selected = _apply_doc_type_tie_break(
        chunks, top_k=2, epsilon=0.03, implementation_doc_types=IMPLEMENTATION_DOC_TYPES
    )

    assert selected == chunks[:2]


# ------------------------------------------------------------------
# hybrid_retrieve: seed-search k widening, gated by the flag
# ------------------------------------------------------------------

def _run_hybrid_capturing_search_payloads(monkeypatch, top_k: int):
    search_payloads = []

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith("/generation"):
            return httpx.Response(200, json={
                "ingestion_id": "generation-1", "generation_status": "ready",
            })
        if request.url.path == "/v1/vectors/search":
            search_payloads.append(json.loads(request.content))
        return httpx.Response(200, json={"results": []})

    real_async_client = httpx.AsyncClient

    def patched_client(*args, **kwargs):
        kwargs["transport"] = httpx.MockTransport(handler)
        return real_async_client(*args, **kwargs)

    monkeypatch.setattr(httpx, "AsyncClient", patched_client)

    asyncio.run(
        hybrid_retrieve(
            query="anything", repo_id="repo-x", query_embedding=[0.0] * 8, top_k=top_k
        )
    )
    return search_payloads


def test_seed_search_uses_top_k_when_flag_disabled(monkeypatch):
    monkeypatch.setenv("DOC_TYPE_TIE_BREAK_ENABLED", "false")
    reset_settings_cache()
    try:
        payloads = _run_hybrid_capturing_search_payloads(monkeypatch, top_k=5)
        assert payloads[0]["k"] == 5
    finally:
        reset_settings_cache()


def test_seed_search_widens_pool_when_flag_enabled(monkeypatch):
    monkeypatch.setenv("DOC_TYPE_TIE_BREAK_ENABLED", "true")
    monkeypatch.setenv("DOC_TYPE_TIE_BREAK_SEED_POOL_SIZE", "100")
    reset_settings_cache()
    try:
        payloads = _run_hybrid_capturing_search_payloads(monkeypatch, top_k=5)
        assert payloads[0]["k"] == 100
    finally:
        reset_settings_cache()
