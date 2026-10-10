"""Failure localization for the small ORIENT evaluation (issue #240).

This module intentionally does not call retrieval or generation.  It consumes
the artifacts already emitted by the query path and applies a fixed decision
table so an orientation failure is not diagnosed from the answer text alone.
The first failing boundary wins, which keeps the controls mutually exclusive.
"""

from dataclasses import dataclass
from typing import Any, Literal

from .provenance_diagnostics import diagnose_manifest

FailureClass = Literal[
    "seed_retrieval",
    "graph_resolution",
    "missing_structural_inventory",
    "authority_evidence",
    "generation",
    "no_failure",
]


@dataclass(frozen=True)
class OrientationObservation:
    """Minimal, serialized evidence needed to localize one orientation case."""

    target_canonical_ids: tuple[str, ...] = ()
    # Targets expected to be reachable from a retrieved anchor through graph
    # expansion.  These are separate from direct seed targets because a graph
    # miss cannot be inferred from a vector-only target.
    graph_target_canonical_ids: tuple[str, ...] = ()
    evidence_trace: tuple[dict[str, Any], ...] = ()
    required_facets: tuple[str, ...] = ()
    orient_response: dict[str, Any] | None = None
    final_context_manifest: tuple[dict[str, Any], ...] = ()
    claim_type: str = "repository_overview"
    answer: str = ""
    expected_answer_terms: tuple[str, ...] = ()


def _trace_by_id(observation: OrientationObservation) -> dict[str, dict[str, Any]]:
    return {
        str(entry["canonical_id"]): entry
        for entry in observation.evidence_trace
        if entry.get("canonical_id") is not None
    }


def _facet_missing(observation: OrientationObservation) -> bool:
    if not observation.required_facets:
        return False
    response = observation.orient_response
    if response is None:
        return True
    gaps = {
        str(gap.get("category"))
        for gap in response.get("gaps", [])
        if isinstance(gap, dict)
    }
    for facet in observation.required_facets:
        value = response.get(facet)
        if facet in gaps or value is None or value == [] or value == {}:
            return True
    return False


def classify_orientation_failure(
    observation: OrientationObservation,
) -> FailureClass:
    """Return the first failing evidence boundary, or ``no_failure``.

    Decision order is deliberate:

    1. seed retrieval: a requested artifact was absent from both seed and
       graph evidence;
    2. graph resolution: a graph-reachable target was seeded/anchored but was
       not discovered by expansion;
    3. structural inventory: the deterministic ORIENT facet is absent or
       explicitly marked as a gap;
    4. authority/evidence: evidence reached final context but provenance says
       it is unsafe for the overview claim;
    5. generation: authoritative evidence reached context but the answer
       misses a pre-registered term.

    A case with no expected answer terms is considered a retrieval/evidence
    control only; it cannot be called a generation failure without a grading
    obligation.
    """
    trace = _trace_by_id(observation)

    for canonical_id in observation.target_canonical_ids:
        entry = trace.get(canonical_id)
        if entry is None or not (
            entry.get("found_by_vector") or entry.get("found_by_graph")
        ):
            return "seed_retrieval"

    for canonical_id in observation.graph_target_canonical_ids:
        entry = trace.get(canonical_id)
        if entry is None or not entry.get("found_by_graph"):
            return "graph_resolution"

    if _facet_missing(observation):
        return "missing_structural_inventory"

    if observation.final_context_manifest:
        findings = diagnose_manifest(
            observation.claim_type, list(observation.final_context_manifest)
        )
        if any(finding.concerns for finding in findings):
            return "authority_evidence"

    if observation.expected_answer_terms:
        answer = observation.answer.casefold()
        if any(
            term.casefold() not in answer
            for term in observation.expected_answer_terms
        ):
            return "generation"

    return "no_failure"
