from src.retrieval.repository_overview_policy import (
    assess_repository_overview,
    render_repository_overview_policy,
)


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
