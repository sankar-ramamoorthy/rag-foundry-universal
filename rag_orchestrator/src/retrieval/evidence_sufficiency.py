# rag_orchestrator/src/retrieval/evidence_sufficiency.py
"""
Bounded evidence-sufficiency assessment (issue #200, Stage A1).

Pure functions: given an already-computed ORIENT response dict or a
TRACE/IMPACT start-resolution result (plus, if resolved, the traversal
result), decide whether a mode's declared obligations are `satisfied`,
`missing`, or `unknown`. No I/O, no retraversal, no LLM call, no retry --
the bounded-repair control loop (Stage A2) and its HTTP surface
(Stage A3) are separate, not-yet-implemented consumers of this module.

Mirrors the Stage A mechanical-check tables in
`DOCS/proposals/2026-09-19-phase-6-sufficiency-authority-handoff.md`.
"Sufficient" means "satisfies declared obligations within this indexed
scope" -- never "proves the answer is true": there is no universal
minimum evidence count, and an empty/truncated IMPACT candidate set is a
valid `satisfied` result, not a failure.

See `specs/007-bounded-evidence-sufficiency/spec.md` for the scenario-
level contract this module implements.
"""

from dataclasses import dataclass, field
from typing import Literal

from src.retrieval.trace_impact import (
    AmbiguousStart,
    ImpactResult,
    ResolvedStart,
    TraceResult,
)

ObligationStatus = Literal["satisfied", "missing", "unknown"]
AssessmentStatus = Literal["satisfied", "partial", "needs_clarification"]

# Bumped whenever the mechanical rule set below changes in a way that
# could flip a prior classification; Stage C's authority-aware policy
# will use a distinct version string so diagnostics can tell the two
# apart (handoff FR: "mechanical success and authority-qualified success
# must be separately visible").
POLICY_VERSION = "stage-a-mechanical-v1"


@dataclass(frozen=True)
class EvidenceItem:
    """One piece of evidence a satisfied obligation points to."""

    identity: str  # canonical_id, or the ORIENT facet name
    kind: Literal["orient_facet", "trace_start", "trace_hop", "impact_candidate"]
    supporting: str | None = None  # relation_type or other basis description


@dataclass(frozen=True)
class EvidenceAssessment:
    policy_version: str
    status: AssessmentStatus
    obligations: dict[str, ObligationStatus]
    reason_codes: list[str]
    evidence: list[EvidenceItem] = field(default_factory=list)
    missing_obligations: list[str] = field(default_factory=list)


def _overall_status(obligations: dict[str, ObligationStatus]) -> AssessmentStatus:
    if all(status == "satisfied" for status in obligations.values()):
        return "satisfied"
    return "partial"


def _missing(obligations: dict[str, ObligationStatus]) -> list[str]:
    return [name for name, status in obligations.items() if status != "satisfied"]


def _unresolved_start_assessment() -> EvidenceAssessment:
    return EvidenceAssessment(
        policy_version=POLICY_VERSION,
        status="partial",
        obligations={"start": "missing"},
        reason_codes=["start:unresolved"],
        missing_obligations=["start"],
    )


def _ambiguous_start_assessment() -> EvidenceAssessment:
    return EvidenceAssessment(
        policy_version=POLICY_VERSION,
        status="needs_clarification",
        obligations={"start": "unknown"},
        reason_codes=["start:ambiguous"],
        missing_obligations=["start"],
    )


def assess_orient(
    orient_response: dict,
    required_facets: list[str],
) -> EvidenceAssessment:
    """ORIENT mechanical check: each required facet either has supported
    records (a non-empty field on the response) or an explicit inventory
    gap ingestion recorded for it; a facet with neither is `unknown` --
    ORIENT itself never accounted for it, so this is not a manufactured
    gap. Duplicate facet names in `required_facets` collapse to one
    obligation."""
    gap_categories = {gap.get("category") for gap in orient_response.get("gaps", [])}
    obligations: dict[str, ObligationStatus] = {}
    reason_codes: list[str] = []
    evidence: list[EvidenceItem] = []

    for facet in dict.fromkeys(required_facets):  # de-dup, preserve order
        value = orient_response.get(facet)
        if value:
            obligations[facet] = "satisfied"
            evidence.append(EvidenceItem(identity=facet, kind="orient_facet"))
        elif facet in gap_categories:
            obligations[facet] = "missing"
            reason_codes.append(f"{facet}:inventory_gap")
        else:
            obligations[facet] = "unknown"
            reason_codes.append(f"{facet}:unsupported_facet")

    return EvidenceAssessment(
        policy_version=POLICY_VERSION,
        status=_overall_status(obligations),
        obligations=obligations,
        reason_codes=reason_codes,
        evidence=evidence,
        missing_obligations=_missing(obligations),
    )


def _assess_target_obligation(
    trace_result: TraceResult, required_target: str
) -> tuple[ObligationStatus, list[str], EvidenceItem | None]:
    """Isolates the target-obligation branch of `assess_trace`: found,
    cut-off-by-a-cap (`unknown`), or genuinely absent (`missing`)."""
    hit = next(
        (hop for hop in trace_result.hops if hop.canonical_id == required_target),
        None,
    )
    if hit is not None:
        item = EvidenceItem(
            identity=hit.canonical_id, kind="trace_hop", supporting=hit.relation_type
        )
        return "satisfied", [], item
    if trace_result.truncated:
        return "unknown", ["target:node_truncated"], None
    if trace_result.depth_limited:
        return "unknown", ["target:depth_limited"], None
    return "missing", ["target:not_in_explored_frontier"], None


def _scope_reason_codes(trace_result: TraceResult) -> list[str]:
    codes = []
    if trace_result.truncated:
        codes.append("scope:node_truncated")
    if trace_result.depth_limited:
        codes.append("scope:depth_limited")
    codes.extend(f"external_gap:{gap.canonical_id}" for gap in trace_result.gaps)
    return codes


def assess_trace(
    resolved: ResolvedStart | AmbiguousStart | None,
    trace_result: TraceResult | None,
    required_target: str | None = None,
) -> EvidenceAssessment:
    """TRACE mechanical check: unique start, requested target if
    supplied, bounded scope. A target absent because the bounded
    frontier was cut off (node cap or depth cap) is `unknown` -- more
    graph may exist past the cap; a target absent from a fully-explored
    frontier is `missing`. Caller must have already resolved `start` and,
    if resolved, called `traced_path`."""
    if resolved is None:
        return _unresolved_start_assessment()
    if isinstance(resolved, AmbiguousStart):
        return _ambiguous_start_assessment()
    if trace_result is None:
        raise ValueError("trace_result is required once `resolved` is a ResolvedStart")

    obligations: dict[str, ObligationStatus] = {"start": "satisfied"}
    evidence = [EvidenceItem(identity=resolved.canonical_id, kind="trace_start")]

    if required_target is None:
        reason_codes = _scope_reason_codes(trace_result)
    else:
        target_status, target_reasons, target_evidence = _assess_target_obligation(
            trace_result, required_target
        )
        obligations["target"] = target_status
        if target_evidence is not None:
            evidence.append(target_evidence)
        reason_codes = [*target_reasons, *_scope_reason_codes(trace_result)]

    return EvidenceAssessment(
        policy_version=POLICY_VERSION,
        status=_overall_status(obligations),
        obligations=obligations,
        reason_codes=reason_codes,
        evidence=evidence,
        missing_obligations=_missing(obligations),
    )


def assess_impact(
    resolved: ResolvedStart | AmbiguousStart | None,
    impact_result: ImpactResult | None,
) -> EvidenceAssessment:
    """IMPACT mechanical check: unique start; the candidate-set
    obligation is always `satisfied` once resolved -- `assess_impact` in
    `trace_impact.py` already guarantees every candidate carries a basis,
    and an empty or truncated candidate set is itself a valid bounded
    result, never a sufficiency failure. Truncation is still surfaced via
    `reason_codes` so a caller can see the bound was hit."""
    if resolved is None:
        return _unresolved_start_assessment()
    if isinstance(resolved, AmbiguousStart):
        return _ambiguous_start_assessment()
    if impact_result is None:
        raise ValueError("impact_result is required once `resolved` is a ResolvedStart")

    reason_codes: list[str] = []
    if impact_result.truncated:
        reason_codes.append("scope:candidate_truncated")

    evidence = [
        EvidenceItem(
            identity=candidate.canonical_id,
            kind="impact_candidate",
            supporting=",".join(basis.relation_type for basis in candidate.basis),
        )
        for candidate in impact_result.candidates
    ]

    obligations: dict[str, ObligationStatus] = {
        "start": "satisfied",
        "candidate_set": "satisfied",
    }
    return EvidenceAssessment(
        policy_version=POLICY_VERSION,
        status="satisfied",
        obligations=obligations,
        reason_codes=reason_codes,
        evidence=evidence,
        missing_obligations=[],
    )
