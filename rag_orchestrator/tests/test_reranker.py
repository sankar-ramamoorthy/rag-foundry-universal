# rag_orchestrator/tests/test_reranker.py
"""
WP-S8: the cross-encoder reranker's core scoring/truncation logic, in
isolation from the retrieval pipeline and the real (heavy, network-
fetched) CrossEncoder model -- a fake `reranker` is injected directly,
same pattern as test_doc_type_tie_break.py isolates
_apply_doc_type_tie_break from hybrid_retrieve.
"""
import pytest

from src.core.reranker import get_reranker, reset_reranker_cache, rerank_chunks

pytestmark = pytest.mark.unit


class _FakeCrossEncoder:
    """Scores each (query, text) pair by a caller-supplied lookup, so
    tests can assert exact resulting order without a real model."""

    def __init__(self, score_by_text: dict[str, float]):
        self._score_by_text = score_by_text
        self.predict_calls: list[list[tuple[str, str]]] = []

    def predict(self, pairs: list[tuple[str, str]]) -> list[float]:
        self.predict_calls.append(pairs)
        return [self._score_by_text[text] for _, text in pairs]


def _chunk(chunk_id: str, text: str) -> dict:
    return {"chunk_id": chunk_id, "text": text, "document_id": f"doc-{chunk_id}"}


def test_rerank_sorts_by_cross_encoder_score_descending():
    """The whole point of reranking: reorder by the cross-encoder's
    judgment, not whatever order chunks arrived in."""
    chunks = [_chunk("a", "low relevance"), _chunk("b", "high relevance")]
    fake = _FakeCrossEncoder({"low relevance": 0.1, "high relevance": 0.9})

    result = rerank_chunks(
        "query", chunks, top_k=10, model_name="unused", reranker=fake
    )

    assert [c["chunk_id"] for c in result] == ["b", "a"]


def test_rerank_truncates_to_top_k():
    """WP-S8: top-50 -> top-10 shape -- the post-rerank cut is real, not
    cosmetic."""
    chunks = [_chunk(str(i), f"text-{i}") for i in range(5)]
    fake = _FakeCrossEncoder({f"text-{i}": float(i) for i in range(5)})

    result = rerank_chunks(
        "query", chunks, top_k=2, model_name="unused", reranker=fake
    )

    # Highest scores are text-4 (score 4) and text-3 (score 3).
    assert [c["chunk_id"] for c in result] == ["4", "3"]


def test_rerank_empty_input_returns_empty():
    fake = _FakeCrossEncoder({})

    result = rerank_chunks("query", [], top_k=10, model_name="unused", reranker=fake)

    assert result == []
    assert fake.predict_calls == [], "must not call predict() on an empty pool"


def test_rerank_top_k_at_or_above_pool_size_still_resorts():
    """top_k >= len(chunks) narrows nothing, but the caller still gets a
    cross-encoder-consistent order, not the original arrival order."""
    chunks = [_chunk("a", "low"), _chunk("b", "high")]
    fake = _FakeCrossEncoder({"low": 0.1, "high": 0.9})

    result = rerank_chunks(
        "query", chunks, top_k=10, model_name="unused", reranker=fake
    )

    assert [c["chunk_id"] for c in result] == ["b", "a"]


def test_rerank_passes_query_and_text_pairs_to_predict():
    chunks = [_chunk("a", "chunk text here")]
    fake = _FakeCrossEncoder({"chunk text here": 0.5})

    rerank_chunks("the query", chunks, top_k=10, model_name="unused", reranker=fake)

    assert fake.predict_calls == [[("the query", "chunk text here")]]


def test_get_reranker_caches_per_model_name(monkeypatch):
    """Loading a CrossEncoder is expensive -- must not reload per request."""
    reset_reranker_cache()
    load_count = {"n": 0}

    class _StubModule:
        class CrossEncoder:
            def __init__(self, model_name):
                load_count["n"] += 1
                self.model_name = model_name

    monkeypatch.setitem(
        __import__("sys").modules, "sentence_transformers", _StubModule()
    )

    first = get_reranker("some-model")
    second = get_reranker("some-model")
    third = get_reranker("other-model")

    assert first is second
    assert first is not third
    assert load_count["n"] == 2  # one per distinct model_name
    reset_reranker_cache()
