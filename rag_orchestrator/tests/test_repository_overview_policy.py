from src.retrieval.repository_overview_policy import (
    assess_repository_overview,
    render_repository_overview_policy,
)
from src.core.service import _prepend_policy_chunks
from src.retrieval.agent_adapter import build_final_context_manifest


def _provenance(role: str, subject: str = "selected_repository") -> dict:
    return {
        "role": {"value": role},
        "subject": {"value": subject},
    }


def test_fixture_and_archived_sources_are_non_authoritative():
    assessment = assess_repository_overview(
        [
            {
                "canonical_id": "docs-archive/PROJECT_PLAN.md",
                "provenance": _provenance("historical"),
            },
            {
                "canonical_id": "shared/smoke_repo/README.md",
                "provenance": _provenance("example_fixture", "embedded_subject"),
            },
        ],
        {"services": []},
    )
    assert assessment["status"] == "qualified_with_non_authoritative_evidence"
    rendered = str(assessment)
    assert "non_current_source_cannot_satisfy_present_structure" in rendered
    assert "embedded_subject_cannot_satisfy_repository_overview" in rendered


def test_missing_inventory_is_an_explicit_gap():
    assessment = assess_repository_overview([], None)
    assert assessment["status"] == "gap"
    assert assessment["gap"] == "current_structural_inventory_unavailable"


def test_policy_prompt_pins_subject_and_forbids_substitution():
    text = render_repository_overview_policy(
        "repo-1",
        None,
        {"status": "gap"},
    )
    assert "Pinned repository subject: repo-1" in text
    assert "Evidence describing another repository cannot satisfy" in text
    assert "do not substitute" in text


def test_canonical_selection_precedes_budget_and_has_its_own_reason():
    selected = {"chunk_id": "purpose", "document_id": "doc-purpose", "text": "purpose"}
    historical = {"chunk_id": "note", "document_id": "doc-note", "text": "note"}
    chunks = _prepend_policy_chunks([historical, selected], [selected], 2)
    assert [chunk["chunk_id"] for chunk in chunks] == ["purpose", "note"]
    manifest = build_final_context_manifest(
        chunks, policy_document_ids={"doc-purpose"}
    )
    assert manifest[0]["selection_reason"] == "repository_overview_canonical_selection"


def test_canonical_selection_respects_chunk_cap_without_duplicates():
    policy = {"chunk_id": "purpose", "document_id": "doc-purpose", "text": "purpose"}
    old = {"chunk_id": "note", "document_id": "doc-note", "text": "note"}
    assert _prepend_policy_chunks([old, policy], [policy], 1) == [policy]
