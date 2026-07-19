# tests/core/vectorstore/test_typed_filter_columns.py
"""
WP-S4B: repo_id/doc_type filters target their typed columns; everything
else stays on the source_metadata JSONB. Pure SQL-construction tests —
no database needed.
"""
import pytest

from src.core.vectorstore.pgvector_store import PgVectorStore

pytestmark = pytest.mark.unit


def render(metadata_filter):
    conditions, values = PgVectorStore._build_filter_conditions(metadata_filter)
    return [c.as_string(None) for c in conditions], values


def test_repo_id_equality_uses_typed_column():
    conditions, values = render({"repo_id": "repo-x"})
    assert conditions == ['vc."repo_id" = %s']
    assert values == ["repo-x"]


def test_doc_type_equality_uses_typed_column():
    conditions, values = render({"doc_type": "code"})
    assert conditions == ['vc."doc_type" = %s']
    assert values == ["code"]


def test_other_keys_stay_on_jsonb():
    conditions, values = render({"canonical_id": "a.py#f"})
    assert conditions == ["vc.source_metadata->>'canonical_id' = %s"]
    assert values == ["a.py#f"]


def test_hybrid_query_filter_shape():
    """The exact filter the orchestrator sends (issue #30 Part 1)."""
    conditions, values = render({"doc_type": "code", "repo_id": "repo-x"})
    assert conditions == ['vc."doc_type" = %s', 'vc."repo_id" = %s']
    assert values == ["code", "repo-x"]


def test_ne_operator_on_typed_column_matches_null():
    conditions, values = render({"doc_type": {"ne": "code"}})
    assert conditions == ['(vc."doc_type" IS NULL OR vc."doc_type" != %s)']
    assert values == ["code"]


def test_ne_operator_on_jsonb_key():
    conditions, values = render({"source_type": {"ne": "code"}})
    assert conditions == [
        "(vc.source_metadata->>'source_type' IS NULL "
        "OR vc.source_metadata->>'source_type' != %s)"
    ]
    assert values == ["code"]


def test_in_operator_on_typed_column():
    conditions, values = render({"doc_type": {"in": ["file", "pdf"]}})
    assert conditions == ['vc."doc_type" IN (%s, %s)']
    assert values == ["file", "pdf"]
