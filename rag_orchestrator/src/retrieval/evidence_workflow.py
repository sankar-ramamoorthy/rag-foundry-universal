# rag_orchestrator/src/retrieval/evidence_workflow.py
"""
Bounded evidence-sufficiency control loop (issue #200, Stage A2).

Pure, synchronous decision logic: given an already-loaded `CodebaseGraph`
(TRACE/IMPACT) or an already-fetched ORIENT response dict (ORIENT), run
the mode's initial mechanical check (Stage A1's `evidence_sufficiency`
assessor), and -- for TRACE only, the one case where Stage A currently
has a permitted repair action available -- one bounded, useful follow-up
if it fits the fixed priority table from the handoff:

    1. Fetch an explicitly missing, already-resolved artifact/passage.
    2. Extend a TRACE/IMPACT frontier to the next permitted depth where
       initial execution deliberately used a smaller scope than the
       server ceiling.
    3. Reassemble context to retain required already-fetched items.

Only repair #2 is implementable without a passage-fetch/context-assembly
seam (those belong to Stage A4). IMPACT's candidate-set obligation is
*always* satisfied (see `evidence_sufficiency.assess_impact`), so IMPACT
never has anything to repair under Stage A: truncation is reported, not
retried. ORIENT has no targeted fact-fetch capability at all yet, so a
`missing`/`unknown` ORIENT facet is reported as a gap, never retried --
manufacturing a new extractor here would violate the handoff's explicit
prohibition.

No I/O happens in this module: the graph/response are already in hand,
and generation fencing (resolving + re-verifying the ingestion
generation around this work) is the caller's job
(`src/core/evidence_service.py`, Stage A2's adapter layer) -- exactly
the "pure controller, I/O isolated in adapters" split the handoff
describes for the assessor.
"""

from dataclasses import dataclass, field, replace
from typing import Literal, Optional

from src.retrieval.codebase_queries import CodebaseGraph
from src.retrieval.evidence_authority import AuthorityAssessment, assess_authority
from src.retrieval.evidence_sufficiency import (
    EvidenceAssessment,
    assess_impact as assess_impact_evidence,
    assess_orient,
    assess_trace,
)
from src.retrieval.provenance_diagnostics import ClaimType
from src.retrieval.trace_impact import (
    AmbiguousStart,
    ImpactResult,
    assess_impact as compute_impact,
    resolve_start_symbol,
    traced_path,
)

# Fixed by the handoff: initial pass + at most one follow-up.
MAX_PASSES = 2
MAX_REPAIR_ACTIONS = 1

StopReason = Literal[
    "satisfied",
    "needs_clarification",
    "unresolved_start",
    "no_repair_capability",
    "no_useful_repair",
    "repair_applied",
]


@dataclass(frozen=True)
class StepRecord:
    action: str
    reason: str
    outcome: Literal["satisfied", "progress", "no_progress"]


@dataclass(frozen=True)
class ExplanationResult:
    """Issue #200, Stage A4: the optional single generation phase over
    the finalized evidence -- `None` fields (other than `skipped_reason`)
    mean generation didn't run at all, never that it ran and returned
    nothing. Populated by `evidence_service.py` (I/O), never by this
    module -- kept here only because it lives on `WorkflowResult`."""

    answer: str | None
    model_used: str | None = None
    model_alias: str | None = None
    fallback_from: str | None = None
    skipped_reason: str | None = None


@dataclass(frozen=True)
class WorkflowResult:
    assessment: EvidenceAssessment
    steps: list[StepRecord] = field(default_factory=list)
    stop_reason: StopReason = "satisfied"
    # Stage A4: absent (None) unless the caller asked for an explanation
    # (an explanation_query was supplied) -- the pure workflow functions
    # in this module never set it themselves.
    explanation: ExplanationResult | None = None
    # Issue #200 (Stage C, follow-up to #199): absent (None) unless the
    # caller supplied claim_type -- see evidence_authority.py. Never
    # gates or replaces `assessment` above; both are always visible
    # together when present.
    authority: AuthorityAssessment | None = None


def _with_authority(
    graph: CodebaseGraph,
    result: WorkflowResult,
    claim_type: Optional[ClaimType],
) -> WorkflowResult:
    if claim_type is None:
        return result
    provenance_by_canonical_id = {
        cid: node.provenance for cid, node in graph.nodes.items()
    }
    authority = assess_authority(
        claim_type, result.assessment, provenance_by_canonical_id
    )
    return replace(result, authority=authority)


def _start_failure_result(
    resolved: AmbiguousStart | None, assess_fn
) -> WorkflowResult:
    assessment = assess_fn(resolved, None)
    stop_reason: StopReason = (
        "needs_clarification"
        if isinstance(resolved, AmbiguousStart)
        else "unresolved_start"
    )
    return WorkflowResult(assessment=assessment, steps=[], stop_reason=stop_reason)


def run_orient_workflow(
    orient_response: dict, required_facets: list[str]
) -> WorkflowResult:
    """ORIENT has no bounded repair action in Stage A: every field is
    already computed once at ingestion time, so a second read of the
    same response can never change the outcome (`Do not retry ... the
    same action with the same inputs`)."""
    assessment = assess_orient(orient_response, required_facets)
    steps = [
        StepRecord(
            action="read_orient_response",
            reason="single deterministic ingestion-time read",
            outcome="satisfied" if assessment.status == "satisfied" else "no_progress",
        )
    ]
    stop_reason: StopReason = (
        "satisfied" if assessment.status == "satisfied" else "no_repair_capability"
    )
    return WorkflowResult(assessment=assessment, steps=steps, stop_reason=stop_reason)


def run_impact_workflow(
    graph: CodebaseGraph,
    start: str,
    max_depth: int,
    max_candidates: int,
    claim_type: Optional[ClaimType] = None,
) -> WorkflowResult:
    """IMPACT's candidate-set obligation is always `satisfied` once
    resolved (an empty/truncated candidate set is itself a valid bounded
    result) -- so there is never an obligation-driven reason to spend a
    repair action here under Stage A. `claim_type` (Stage C) only adds
    an authority assessment alongside this; it changes nothing above."""
    result = _run_impact_workflow(graph, start, max_depth, max_candidates)
    return _with_authority(graph, result, claim_type)


def _run_impact_workflow(
    graph: CodebaseGraph,
    start: str,
    max_depth: int,
    max_candidates: int,
) -> WorkflowResult:
    resolved = resolve_start_symbol(graph, start)
    if resolved is None or isinstance(resolved, AmbiguousStart):
        return _start_failure_result(resolved, assess_impact_evidence)

    result: ImpactResult = compute_impact(
        graph, resolved.canonical_id, max_depth=max_depth, max_candidates=max_candidates
    )
    assessment = assess_impact_evidence(resolved, result)
    steps = [
        StepRecord(
            action="compute_impact",
            reason=f"max_depth={max_depth}",
            outcome="satisfied",
        )
    ]
    return WorkflowResult(assessment=assessment, steps=steps, stop_reason="satisfied")


def run_trace_workflow(
    graph: CodebaseGraph,
    start: str,
    relation_types: set[str] | None,
    direction: str,
    requested_max_depth: int,
    server_max_depth: int,
    max_nodes: int,
    required_target: str | None = None,
    claim_type: Optional[ClaimType] = None,
) -> WorkflowResult:
    """One bounded repair: if the target obligation came back `unknown`
    because the requested depth (deliberately smaller than the server
    ceiling) cut the frontier off, retry once at the server ceiling.
    Never repairs a `missing` target (fully-explored frontier, more
    depth cannot help) or when the request already ran at the ceiling.
    `claim_type` (Stage C) only adds an authority assessment over the
    final evidence; it changes nothing about the repair decision above."""
    result = _run_trace_workflow(
        graph,
        start,
        relation_types,
        direction,
        requested_max_depth,
        server_max_depth,
        max_nodes,
        required_target,
    )
    return _with_authority(graph, result, claim_type)


def _run_trace_workflow(
    graph: CodebaseGraph,
    start: str,
    relation_types: set[str] | None,
    direction: str,
    requested_max_depth: int,
    server_max_depth: int,
    max_nodes: int,
    required_target: str | None = None,
) -> WorkflowResult:
    resolved = resolve_start_symbol(graph, start)
    if resolved is None or isinstance(resolved, AmbiguousStart):
        return WorkflowResult(
            assessment=assess_trace(resolved, None, required_target),
            steps=[],
            stop_reason=(
                "needs_clarification"
                if isinstance(resolved, AmbiguousStart)
                else "unresolved_start"
            ),
        )

    trace = traced_path(
        graph,
        resolved.canonical_id,
        relation_types,
        direction,
        requested_max_depth,
        max_nodes,
    )
    assessment = assess_trace(resolved, trace, required_target)
    steps = [
        StepRecord(
            action="traced_path",
            reason=f"max_depth={requested_max_depth}",
            outcome="satisfied" if assessment.status == "satisfied" else "no_progress",
        )
    ]
    if assessment.status == "satisfied":
        return WorkflowResult(assessment, steps, "satisfied")

    can_repair = (
        required_target is not None
        and assessment.obligations.get("target") == "unknown"
        and requested_max_depth < server_max_depth
    )
    if not can_repair:
        return WorkflowResult(assessment, steps, "no_useful_repair")

    repaired_trace = traced_path(
        graph,
        resolved.canonical_id,
        relation_types,
        direction,
        server_max_depth,
        max_nodes,
    )
    repaired_assessment = assess_trace(resolved, repaired_trace, required_target)
    prior_target_status = assessment.obligations.get("target")
    new_target_status = repaired_assessment.obligations.get("target")
    progressed = new_target_status != prior_target_status
    steps.append(
        StepRecord(
            action="extend_frontier_to_server_ceiling",
            reason=(
                f"target {prior_target_status} at depth {requested_max_depth}; "
                f"retried at {server_max_depth}"
            ),
            outcome="progress" if progressed else "no_progress",
        )
    )
    return WorkflowResult(repaired_assessment, steps, "repair_applied")
