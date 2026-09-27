"""Controlled Issue #240 ORIENT failure-localization evaluation."""

import pytest

from src.retrieval.orientation_failure import (
    OrientationObservation,
    classify_orientation_failure,
)


def _trace(canonical_id: str, **values: object) -> dict[str, object]:
    return {"canonical_id": canonical_id, **values}


@pytest.mark.parametrize(
    ("observation", "expected"),
    [
        (
            OrientationObservation(
                target_canonical_ids=("docs/architecture.md",),
                evidence_trace=(_trace("docs/architecture.md"),),
            ),
            "seed_retrieval",
        ),
        (
            OrientationObservation(
                graph_target_canonical_ids=("compose:docker-compose.yml#api",),
                evidence_trace=(
                    _trace(
                        "compose:docker-compose.yml#api",
                        found_by_vector=True,
                        found_by_graph=False,
                    ),
                ),
            ),
            "graph_resolution",
        ),
        (
            OrientationObservation(
                required_facets=("services",),
                orient_response={"services": [], "gaps": []},
            ),
            "missing_structural_inventory",
        ),
        (
            OrientationObservation(
                final_context_manifest=(
                    {
                        "canonical_id": "DOCS/test-results/fixture.md",
                        "provenance": {
                            "subject": {"value": "embedded_subject"},
                            "role": {"value": "example_fixture"},
                            "validity": {"declared_status": "current"},
                        },
                    },
                ),
            ),
            "authority_evidence",
        ),
        (
            OrientationObservation(
                final_context_manifest=(
                    {
                        "canonical_id": "README.md",
                        "provenance": {
                            "subject": {"value": "selected_repository"},
                            "role": {"value": "documentation"},
                            "validity": {"declared_status": "current"},
                        },
                    },
                ),
                expected_answer_terms=("rag-foundry-universal", "Docker"),
                answer="This repository is rag-foundry-universal.",
            ),
            "generation",
        ),
    ],
)
def test_control_case_localizes_to_one_failure_class(observation, expected):
    assert classify_orientation_failure(observation) == expected


def test_clean_case_requires_authoritative_evidence_and_answer_terms():
    observation = OrientationObservation(
        final_context_manifest=(
            {
                "canonical_id": "README.md",
                "provenance": {
                    "subject": {"value": "selected_repository"},
                    "role": {"value": "documentation"},
                    "validity": {"declared_status": "current"},
                },
            },
        ),
        expected_answer_terms=("rag-foundry-universal", "Docker"),
        answer="rag-foundry-universal uses Docker.",
    )
    assert classify_orientation_failure(observation) == "no_failure"
