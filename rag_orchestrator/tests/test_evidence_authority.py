# rag_orchestrator/tests/test_evidence_authority.py
"""
Issue #200 (Stage C, follow-up to #199): pure function tests for
authority-aware sufficiency over TRACE/IMPACT evidence -- no DB/HTTP.
Reuses provenance_diagnostics.py's rules; these tests focus on the
aggregation into an overall AuthorityStatus and the "never replaces
mechanical assessment" boundary.
"""

import pytest

from src.retrieval.evidence_authority import assess_authority
from src.retrieval.evidence_sufficiency import EvidenceAssessment, EvidenceItem

pytestmark = pytest.mark.unit


def _mechanical(*identities: str) -> EvidenceAssessment:
    return EvidenceAssessment(
        policy_version="stage-a-mechanical-v1",
        status="satisfied",
        obligations={"start": "satisfied"},
        reason_codes=[],
        evidence=[EvidenceItem(identity=i, kind="trace_hop") for i in identities],
        missing_obligations=[],
    )


def _provenance(role, subject, declared_status="unknown"):
    return {
        "role": {"value": role, "basis": "test"},
        "subject": {"value": subject, "basis": None},
        "derivation": {"status": "source"},
        "validity": {"declared_status": declared_status},
        "classification": {
            "schema_version": "provenance-v1",
            "classifier_version": "role-subject-v2",
            "scope": "artifact",
        },
    }


def test_no_claim_type_is_not_evaluated():
    result = assess_authority(None, _mechanical("a.py#foo"), {})
    assert result.status == "not_evaluated"
    assert result.findings == []


def test_no_evidence_is_not_evaluated_even_with_claim_type():
    empty = EvidenceAssessment(
        policy_version="stage-a-mechanical-v1",
        status="partial",
        obligations={"start": "missing"},
        reason_codes=["start:unresolved"],
        evidence=[],
        missing_obligations=["start"],
    )
    result = assess_authority("implemented_behavior", empty, {})
    assert result.status == "not_evaluated"


def test_real_implementation_is_authority_qualified():
    assessment = _mechanical("src/foo.py#run")
    provenance = {
        "src/foo.py#run": _provenance("implementation", "selected_repository")
    }
    result = assess_authority("implemented_behavior", assessment, provenance)
    assert result.status == "authority_qualified"
    assert all(f.concerns == [] for f in result.findings)


def test_embedded_example_is_authority_unqualified():
    """The handoff's core acceptance case: mechanically satisfied, but
    all support concerns an embedded example -- must be flagged, never
    silently accepted as qualified."""
    assessment = _mechanical("fixtures/example.py#run")
    provenance = {
        "fixtures/example.py#run": _provenance("example_fixture", "embedded_subject")
    }
    result = assess_authority("implemented_behavior", assessment, provenance)
    assert result.status == "authority_unqualified"
    assert "embedded_subject_offered_as_implementation" in result.findings[0].concerns


def test_explicitly_requested_example_via_test_contract_claim_still_qualifies():
    """The handoff's second acceptance case: a valid, explicitly
    requested example (claim_type=test_contract, appropriate for
    inspecting a fixture) must still pass -- test_contract has no rule
    against example_fixture/embedded_subject."""
    assessment = _mechanical("fixtures/example.py#run")
    provenance = {
        "fixtures/example.py#run": _provenance("example_fixture", "embedded_subject")
    }
    result = assess_authority("test_contract", assessment, provenance)
    assert result.status == "authority_qualified"


def test_missing_provenance_is_authority_unknown_not_unqualified():
    assessment = _mechanical("legacy.py#run")
    result = assess_authority("implemented_behavior", assessment, {})
    assert result.status == "authority_unknown"


def test_real_concern_outranks_unknown_provenance_in_same_batch():
    assessment = _mechanical("fixtures/a.py#x", "legacy.py#y")
    provenance = {
        "fixtures/a.py#x": _provenance("example_fixture", "embedded_subject"),
        # "legacy.py#y" absent -> unknown_provenance
    }
    result = assess_authority("implemented_behavior", assessment, provenance)
    assert result.status == "authority_unqualified"


def test_superseded_adr_is_authority_unqualified():
    assessment = _mechanical("DOCS/adr/old.md")
    provenance = {
        "DOCS/adr/old.md": _provenance(
            "design", "selected_repository", declared_status="superseded"
        )
    }
    result = assess_authority("implemented_behavior", assessment, provenance)
    assert result.status == "authority_unqualified"
    assert "superseded_source_offered_as_current" in result.findings[0].concerns


def test_authority_assessment_never_mutates_mechanical_assessment():
    assessment = _mechanical("fixtures/example.py#run")
    provenance = {
        "fixtures/example.py#run": _provenance("example_fixture", "embedded_subject")
    }
    result = assess_authority("implemented_behavior", assessment, provenance)
    # Stage C never touches Stage A's own result -- still "satisfied"
    # mechanically even though authority-unqualified.
    assert assessment.status == "satisfied"
    assert result.status == "authority_unqualified"
