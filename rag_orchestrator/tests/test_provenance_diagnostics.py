# rag_orchestrator/tests/test_provenance_diagnostics.py
"""
Issue #199, Stage B3: pure function tests for the provenance shadow
diagnostics -- no DB/HTTP, no ranking/filtering, informational findings
only. See provenance_diagnostics.py's module docstring for the explicit
constraint this enforces: query-purpose-aware, deterministic, no
universal score, no broad hard filtering.
"""

import pytest

from src.retrieval.provenance_diagnostics import diagnose_manifest

pytestmark = pytest.mark.unit


def _entry(canonical_id, role, subject, declared_status="unknown"):
    return {
        "canonical_id": canonical_id,
        "chunk_id": f"chunk-{canonical_id}",
        "provenance": {
            "role": {"value": role, "basis": "test"},
            "subject": {"value": subject, "basis": None},
            "derivation": {"status": "source"},
            "validity": {"declared_status": declared_status},
            "classification": {
                "schema_version": "provenance-v1",
                "classifier_version": "role-subject-v1",
                "scope": "artifact",
            },
        },
    }


def _entry_no_provenance(canonical_id):
    return {
        "canonical_id": canonical_id,
        "chunk_id": f"chunk-{canonical_id}",
        "provenance": None,
    }


# --- implemented_behavior ---


def test_implemented_behavior_flags_embedded_subject():
    manifest = [_entry("fixtures/example.py", "example_fixture", "embedded_subject")]
    findings = diagnose_manifest("implemented_behavior", manifest)
    assert findings[0].concerns == [
        "embedded_subject_offered_as_implementation",
        "non_implementation_role_offered_as_implementation",
    ]


def test_implemented_behavior_flags_superseded_validity():
    manifest = [
        _entry(
            "DOCS/adr/old.md",
            "design",
            "selected_repository",
            declared_status="superseded",
        )
    ]
    findings = diagnose_manifest("implemented_behavior", manifest)
    assert set(findings[0].concerns) == {
        "non_implementation_role_offered_as_implementation",
        "superseded_source_offered_as_current",
    }


def test_implemented_behavior_real_implementation_has_no_concerns():
    manifest = [_entry("src/foo.py", "implementation", "selected_repository")]
    findings = diagnose_manifest("implemented_behavior", manifest)
    assert findings[0].concerns == []


def test_implemented_behavior_configuration_role_is_not_flagged():
    """Deliberately lenient: a config file may be exactly the right
    answer to an implementation question -- flagging it would be the
    broad hard filtering this stage must not introduce."""
    manifest = [_entry("pyproject.toml", "configuration", "selected_repository")]
    findings = diagnose_manifest("implemented_behavior", manifest)
    assert findings[0].concerns == []


# --- repository_overview ---


def test_repository_overview_flags_embedded_subject():
    manifest = [_entry("fixtures/example.py", "implementation", "embedded_subject")]
    findings = diagnose_manifest("repository_overview", manifest)
    assert findings[0].concerns == ["embedded_subject_in_overview"]


def test_repository_overview_selected_repository_has_no_concerns():
    manifest = [_entry("src/foo.py", "implementation", "selected_repository")]
    findings = diagnose_manifest("repository_overview", manifest)
    assert findings[0].concerns == []


# --- design_rationale / test_contract: deliberately no rules yet ---


def test_design_rationale_never_flags_anything_yet():
    manifest = [
        _entry("fixtures/example.py", "example_fixture", "embedded_subject"),
        _entry("DOCS/adr/old.md", "design", "selected_repository", "superseded"),
        _entry("src/foo.py", "implementation", "selected_repository"),
    ]
    findings = diagnose_manifest("design_rationale", manifest)
    assert all(f.concerns == [] for f in findings)


def test_test_contract_never_flags_anything_yet():
    manifest = [_entry("fixtures/example.py", "example_fixture", "embedded_subject")]
    findings = diagnose_manifest("test_contract", manifest)
    assert findings[0].concerns == []


# --- unknown provenance is its own concern, never guessed either way ---


def test_missing_provenance_is_unknown_provenance_concern():
    manifest = [_entry_no_provenance("legacy.py")]
    findings = diagnose_manifest("implemented_behavior", manifest)
    assert findings[0].concerns == ["unknown_provenance"]


# --- shape guarantees: one finding per entry, order preserved, silence recorded ---


def test_one_finding_per_entry_same_order():
    manifest = [
        _entry("a.py", "implementation", "selected_repository"),
        _entry("b.py", "example_fixture", "embedded_subject"),
    ]
    findings = diagnose_manifest("implemented_behavior", manifest)
    assert [f.canonical_id for f in findings] == ["a.py", "b.py"]
    assert findings[0].concerns == []
    assert findings[1].concerns != []


def test_empty_manifest_yields_empty_findings():
    assert diagnose_manifest("implemented_behavior", []) == []
