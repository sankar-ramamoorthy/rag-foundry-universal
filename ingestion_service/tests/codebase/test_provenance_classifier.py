# ingestion_service/tests/codebase/test_provenance_classifier.py
"""
Issue #199, Stage B1: pure function tests for deterministic role/subject/
derivation/validity classification -- no DB/HTTP. See ADR-053 and
specs/008-source-authority-provenance/spec.md for the contract.
"""

import pytest

from src.core.codebase.provenance_classifier import (
    CLASSIFIER_VERSION,
    SCHEMA_VERSION,
    classify_node,
)

pytestmark = pytest.mark.unit


def test_implementation_file_classified_as_implementation_and_selected_repo():
    result = classify_node(
        relative_path="rag_orchestrator/src/core/service.py",
        doc_type="python source",
        text="def run_rag(): ...",
    )
    assert result["role"]["value"] == "implementation"
    assert result["subject"]["value"] == "selected_repository"
    assert result["subject"]["basis"] is None
    assert result["derivation"] == {"status": "source"}
    assert result["validity"] == {"declared_status": "unknown"}
    assert result["classification"]["schema_version"] == SCHEMA_VERSION
    assert result["classification"]["classifier_version"] == CLASSIFIER_VERSION


def test_test_file_classified_as_test():
    result = classify_node(
        relative_path="rag_orchestrator/tests/test_evidence_workflow.py",
        doc_type="python source",
        text="",
    )
    assert result["role"]["value"] == "test"


def test_fixture_file_classified_as_example_fixture_and_embedded_subject():
    result = classify_node(
        relative_path="ingestion_service/tests/fixtures/rust_repo/crate_a/lib.rs",
        doc_type="rust source",
        text="",
    )
    assert result["role"]["value"] == "example_fixture"
    assert result["subject"]["value"] == "embedded_subject"
    assert result["subject"]["basis"] == "path_convention:fixtures_or_examples_dir"


def test_docs_archive_classified_as_historical():
    result = classify_node(
        relative_path="docs-archive/status-snapshots-2025-2026/2025-06-01.md",
        doc_type="markdown_module",
        text="",
    )
    assert result["role"]["value"] == "historical"


def test_adr_classified_as_design():
    result = classify_node(
        relative_path="DOCS/adr/ADR-053-source-authority-provenance-model.md",
        doc_type="markdown_module",
        text="",
    )
    assert result["role"]["value"] == "design"


def test_manifest_classified_as_configuration():
    result = classify_node(
        relative_path="rag_orchestrator/pyproject.toml",
        doc_type="unknown",
        text="",
    )
    assert result["role"]["value"] == "configuration"


def test_docs_dir_classified_as_documentation():
    result = classify_node(
        relative_path="DOCS/status.md",
        doc_type="markdown_module",
        text="",
    )
    assert result["role"]["value"] == "documentation"


def test_no_matching_rule_is_unknown_mixed_not_guessed():
    result = classify_node(
        relative_path="README.md",
        doc_type="markdown_module",
        text="",
    )
    assert result["role"]["value"] == "unknown_mixed"
    assert result["role"]["basis"] == "no_matching_rule"


def test_declared_status_read_from_frontmatter():
    text = "---\ntitle: Example\nstatus: superseded\n---\n\n# Example\n"
    result = classify_node(
        relative_path="DOCS/adr/ADR-999-example.md",
        doc_type="markdown_module",
        text=text,
    )
    assert result["validity"] == {"declared_status": "superseded"}


def test_no_frontmatter_is_unknown_validity():
    result = classify_node(
        relative_path="DOCS/adr/ADR-999-example.md",
        doc_type="markdown_module",
        text="# No frontmatter here\n",
    )
    assert result["validity"] == {"declared_status": "unknown"}


def test_frontmatter_without_status_field_is_unknown_validity():
    text = "---\ntitle: Example\n---\n\n# Example\n"
    result = classify_node(
        relative_path="DOCS/adr/ADR-999-example.md",
        doc_type="markdown_module",
        text=text,
    )
    assert result["validity"] == {"declared_status": "unknown"}


def test_classification_envelope_present_on_every_result():
    result = classify_node(relative_path="x.py", doc_type="python source", text="")
    assert result["classification"] == {
        "schema_version": SCHEMA_VERSION,
        "classifier_version": CLASSIFIER_VERSION,
        "scope": "artifact",
    }
