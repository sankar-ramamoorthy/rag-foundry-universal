"""WP-R4: payload accounting must include labels, code and Unicode."""
import pytest

from src.retrieval.agent_adapter import (
    assemble_context, build_final_context_manifest, build_sources,
)

pytestmark = pytest.mark.unit


def test_oversized_passage_does_not_hide_later_evidence():
    chunks = [
        {"text": "x" * 500, "document_id": "large"},
        {"text": "return 42", "document_id": "answer", "chunk_index": 19},
    ]
    assembled = assemble_context(chunks, 40)
    assert assembled.text == "[Source: answer]\nreturn 42"
    assert assembled.token_count == len(assembled.text.encode("utf-8"))
    assert build_sources(assembled.chunks) == ["answer"]
    manifest = build_final_context_manifest(assembled.chunks)
    assert [row["source_label"] for row in manifest] == ["answer"]
    assert manifest[0]["chunk_index"] == 19


def test_labels_separators_and_unicode_are_budgeted():
    chunks = [{"text": "你好()", "document_id": "a"}] * 2
    full = assemble_context(chunks, 1000)
    cost = len(full.text.encode("utf-8"))
    assert full.token_count == cost
    assert len(assemble_context(chunks, cost).chunks) == 2
    assert len(assemble_context(chunks, cost - 1).chunks) == 1
    assert assemble_context(chunks, 0).text == ""
