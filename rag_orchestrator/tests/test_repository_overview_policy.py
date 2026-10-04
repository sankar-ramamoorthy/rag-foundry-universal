from src.retrieval.repository_overview_policy import (
    assess_repository_overview,
    canonical_evidence_ids,
    evidence_obligation,
    render_repository_overview_policy,
    select_current_evidence,
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
    manifest = build_final_context_manifest(chunks, policy_document_ids={"doc-purpose"})
    assert manifest[0]["selection_reason"] == "repository_overview_canonical_selection"


def test_canonical_selection_respects_chunk_cap_without_duplicates():
    policy = {"chunk_id": "purpose", "document_id": "doc-purpose", "text": "purpose"}
    old = {"chunk_id": "note", "document_id": "doc-note", "text": "note"}
    assert _prepend_policy_chunks([old, policy], [policy], 1) == [policy]


def test_frozen_questions_have_distinct_evidence_obligations():
    queries = {
        "I need information about the repo structure.": "current_structure",
        "Give me an architectural map of this repository.": "current_architecture",
        "What is this repository about?": "repository_purpose",
        "What does rag-foundry-universal do?": "repository_purpose",
        "Describe this project's purpose and the kinds of source it analyzes.": (
            "repository_purpose"
        ),
        "According to the repository-understanding note, what went wrong?": (
            "explicit_source"
        ),
        "What is shared/smoke_repo used for?": "explicit_source",
        "What does GraphAssembler.assemble do?": "current_behavior",
    }
    for query, expected in queries.items():
        assert evidence_obligation(query) == expected
    assert canonical_evidence_ids("current_structure") == ()
    assert canonical_evidence_ids("repository_purpose") == (
        "CLAUDE.md#claude_md.what_this_project_is",
    )
    assert canonical_evidence_ids("current_architecture") == (
        "shared/config/service_urls.py",
        "README.md#architecture",
    )


def test_historical_and_embedded_evidence_survives_explicit_request_only():
    chunks = [
        {
            "canonical_id": "DOCS/notes/old.md#case",
            "provenance": _provenance("documentation"),
        },
        {
            "canonical_id": "shared/smoke_repo/README.md",
            "provenance": _provenance("example_fixture", "embedded_subject"),
        },
        {
            "canonical_id": "CLAUDE.md#claude_md.what_this_project_is",
            "provenance": _provenance("unknown_mixed"),
        },
    ]
    current, excluded = select_current_evidence(chunks, "repository_purpose")
    assert [c["canonical_id"] for c in current] == [chunks[2]["canonical_id"]]
    assert len(excluded) == 2
    requested, excluded = select_current_evidence(chunks, "explicit_source")
    assert requested == chunks
    assert excluded == []


def test_purpose_uses_canonical_passage_when_present():
    chunks = [
        {"canonical_id": "README.md#architecture"},
        {"canonical_id": "CLAUDE.md#claude_md.what_this_project_is"},
    ]
    selected, excluded = select_current_evidence(chunks, "repository_purpose")
    assert selected == [chunks[1]]
    assert excluded == [
        {
            "canonical_id": "README.md#architecture",
            "reason": "outside_selected_claim_evidence",
        }
    ]


def test_structure_uses_inventory_without_vector_passages():
    chunks = [{"canonical_id": "DOCS/proposals/old.md#layout"}]
    selected, excluded = select_current_evidence(chunks, "current_structure")
    assert selected == []
    assert excluded[0]["reason"] == "orient_inventory_authoritative_for_structure"


def test_architecture_keeps_current_selected_sources_only():
    chunks = [
        {"canonical_id": "README.md#architecture"},
        {"canonical_id": "shared/config/service_urls.py"},
        {"canonical_id": "DOCS/architecture/ms4-old-plan.md#diagram"},
    ]
    selected, excluded = select_current_evidence(chunks, "current_architecture")
    assert selected == chunks[:2]
    assert excluded[0]["canonical_id"] == chunks[2]["canonical_id"]


def test_service_declaration_count_is_distinguished_from_unique_names():
    text = render_repository_overview_policy(
        "repo-1",
        {
            "services": [
                {
                    "name": "api",
                    "compose_file": "main.yml",
                    "dockerfile": "api/Dockerfile",
                },
                {
                    "name": "api",
                    "compose_file": "test.yml",
                    "dockerfile": "api/Dockerfile",
                },
                {"name": "db", "compose_file": "main.yml", "dockerfile": None},
            ],
            "manifests": [{"path": "api/pyproject.toml"}],
            "test_dirs": [],
        },
        {"status": "qualified"},
        repository_name="owner/repo",
    )
    assert "2 distinct service names, 3 Compose declarations" in text
    assert "Verified repository name: owner/repo" in text
    assert "db: Compose files ['main.yml']; Dockerfiles none listed" in text
