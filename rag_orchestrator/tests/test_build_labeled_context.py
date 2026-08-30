# rag_orchestrator/tests/test_build_labeled_context.py
"""
WP-Q0 Q7 finding (DOCS/test_results/2026-08-27-wp-q0-rag-quality-baseline.md):
chunks that share surface phrasing (e.g. "p95 latency") but describe
different referents get conflated by the model when the assembled
context doesn't distinguish which document/section each chunk came
from. build_labeled_context prefixes each chunk with its source label.
"""
import pytest

from src.retrieval.agent_adapter import build_labeled_context

pytestmark = pytest.mark.unit


def chunk(text, canonical_id=None, relative_path=None, document_id="uuid-1"):
    metadata = {}
    if canonical_id:
        metadata["canonical_id"] = canonical_id
    if relative_path:
        metadata["relative_path"] = relative_path
    return {
        "text": text,
        "document_id": document_id,
        "chunk_id": "c",
        "metadata": metadata,
    }


def test_labels_distinguish_similarly_worded_chunks():
    chunks = [
        chunk(
            "p95 ≈ 62 ms in the Phase 1 benchmark",
            canonical_id="README.md#performance_phase_1_baseline",
        ),
        chunk(
            "Vector search p95 @ 1M chunks | seconds (seq scan) | < 100 ms",
            canonical_id="04-Scalability-Plan.md#wp_s4",
        ),
    ]
    context_str, _ = build_labeled_context(chunks, max_total_tokens=4096)
    assert "[Source: README.md#performance_phase_1_baseline]" in context_str
    assert "[Source: 04-Scalability-Plan.md#wp_s4]" in context_str
    # each label immediately precedes its own chunk's text, not the other's
    assert context_str.index("[Source: README.md#performance_phase_1_baseline]") < \
        context_str.index("p95 ≈ 62 ms")
    assert context_str.index("[Source: 04-Scalability-Plan.md#wp_s4]") < \
        context_str.index("seconds (seq scan)")


def test_falls_back_to_relative_path_then_document_id():
    chunks = [
        chunk("a", relative_path="docs/readme.md", document_id="uuid-1"),
        chunk("b", document_id="uuid-2"),
    ]
    context_str, _ = build_labeled_context(chunks, max_total_tokens=4096)
    assert "[Source: docs/readme.md]\na" in context_str
    assert "[Source: uuid-2]\nb" in context_str


def test_no_label_falls_back_to_bare_text():
    chunks = [{"text": "x", "document_id": None, "metadata": None}]
    context_str, _ = build_labeled_context(chunks, max_total_tokens=4096)
    assert context_str == "x"
    assert "[Source:" not in context_str


def test_token_budget_still_truncates():
    chunks = [
        chunk("one two three", canonical_id="a.py#f"),
        chunk("four five six", canonical_id="b.py#g"),
    ]
    context_str, token_count = build_labeled_context(chunks, max_total_tokens=3)
    assert "a.py#f" in context_str
    assert "b.py#g" not in context_str
    assert token_count == 3


def test_empty_input():
    assert build_labeled_context([], max_total_tokens=4096) == ("", 0)
