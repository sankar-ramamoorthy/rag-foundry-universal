# rag_orchestrator/src/core/evidence_service.py
"""
Bounded evidence-sufficiency workflow adapters (issue #200, Stage A2).

Isolates every I/O call the ORIENT/TRACE/IMPACT evidence workflows need
(HTTP fetch to ingestion_service, in-memory graph load) and wraps each
one in a generation fence: resolve the currently-ready generation once,
do the work, then verify the generation has not changed before trusting
the result -- reusing the same ready-generation pattern `run_rag()`
already relies on (`_query_generation`/`_verify_generation` in
`service.py`, ADR-052), rather than inventing a second one for this
workflow.

The actual decision logic (what counts as sufficient, whether a bounded
repair is worth attempting) is pure and lives in
`src/retrieval/evidence_workflow.py` (Stage A1's assessor plus Stage
A2's one-repair control loop) -- this module's only job is I/O plus
fencing around it.
"""

import logging
from dataclasses import replace

import httpx
from fastapi import HTTPException

from src.core.config import get_settings
from src.core.service import _query_generation, _verify_generation
from src.retrieval.codebase_utils import get_cached_graph_with_generation
from src.retrieval.evidence_sufficiency import EvidenceAssessment
from src.retrieval.evidence_workflow import (
    ExplanationResult,
    WorkflowResult,
    run_impact_workflow,
    run_orient_workflow,
    run_trace_workflow,
)
from src.retrieval.provenance_diagnostics import ClaimType

logger = logging.getLogger(__name__)


async def fetch_orient_response(repo_id: str) -> dict:
    """HTTP GET to ingestion_service's deterministic ORIENT endpoint
    (issue #197). Preserves ingestion_service's own 404 (no completed
    generation) and 409 (generation predates ORIENT) rather than
    collapsing every failure into one generic status -- the same
    contract `routes.py`'s `/repos/{repo_id}/orient` passthrough
    exposes directly; this is the shared implementation both use."""
    settings = get_settings()
    url = f"{settings.INGESTION_SERVICE_URL}/v1/repos/{repo_id}/orient"
    try:
        async with httpx.AsyncClient(timeout=30) as client:
            resp = await client.get(url)
    except httpx.HTTPError as exc:
        logger.error(f"Failed to reach ingestion_service for ORIENT: {exc}")
        raise HTTPException(502, "ingestion_service unavailable") from exc

    if resp.status_code == 200:
        return resp.json()
    if resp.status_code in (404, 409):
        try:
            detail = resp.json().get("detail", resp.text)
        except ValueError:
            detail = resp.text
        raise HTTPException(resp.status_code, detail)
    logger.error(
        f"ingestion_service returned unexpected status {resp.status_code} "
        f"for ORIENT (repo_id={repo_id[:8]})"
    )
    raise HTTPException(502, "ingestion_service returned an unexpected error")


def _render_evidence_context(mode: str, assessment: EvidenceAssessment) -> str:
    """Issue #200, Stage A4: a deterministic textual rendering of the
    finalized assessment -- exactly the identities/kinds/relations/reason
    codes already computed, nothing invented. This is what "evidence-to-
    prompt survival" means here: the structural facts that were actually
    found are what the LLM sees, byte for byte, not a paraphrase built
    from raw source text (that's `/v1/rag`'s job, a different endpoint)."""
    lines = [f"mode: {mode}", f"status: {assessment.status}"]
    for name, status in assessment.obligations.items():
        lines.append(f"obligation {name}: {status}")
    if assessment.evidence:
        lines.append("evidence:")
        for item in assessment.evidence:
            suffix = f" ({item.supporting})" if item.supporting else ""
            lines.append(f"- [{item.kind}] {item.identity}{suffix}")
    if assessment.reason_codes:
        lines.append("reason_codes: " + ", ".join(assessment.reason_codes))
    if assessment.missing_obligations:
        lines.append(
            "missing_obligations: " + ", ".join(assessment.missing_obligations)
        )
    return "\n".join(lines)


async def _generate_evidence_explanation(
    mode: str,
    assessment: EvidenceAssessment,
    explanation_query: str,
    provider: str | None,
    model: str | None,
) -> ExplanationResult:
    """The one generation phase Stage A4 allows, run only after the
    workflow's final assessment is in hand -- never mid-repair, never
    more than once per request. `needs_clarification` or genuinely no
    evidence skips generation entirely rather than asking the model to
    explain nothing (handoff: "absent evidence returns an explicit gap
    response")."""
    if assessment.status == "needs_clarification":
        return ExplanationResult(
            answer=None, skipped_reason="start is ambiguous; nothing to explain"
        )
    if not assessment.evidence:
        return ExplanationResult(
            answer=None, skipped_reason="no supported evidence to explain"
        )

    settings = get_settings()
    payload = {
        "context": _render_evidence_context(mode, assessment),
        "query": explanation_query,
    }
    params: dict[str, str] = {}
    if provider:
        params["provider"] = provider
    if model:
        params["model"] = model

    url = f"{settings.LLM_SERVICE_URL}/generate"
    async with httpx.AsyncClient(timeout=200) as client:
        resp = await client.post(url, json=payload, params=params)
        resp.raise_for_status()
        result = resp.json()

    return ExplanationResult(
        answer=result.get("response", ""),
        model_used=result.get("model"),
        model_alias=result.get("model_alias"),
        fallback_from=result.get("fallback_from"),
    )


async def _with_explanation(
    mode: str,
    result: WorkflowResult,
    explanation_query: str | None,
    provider: str | None,
    model: str | None,
) -> WorkflowResult:
    if explanation_query is None:
        return result
    explanation = await _generate_evidence_explanation(
        mode, result.assessment, explanation_query, provider, model
    )
    return replace(result, explanation=explanation)


async def run_orient_evidence(
    repo_id: str,
    required_facets: list[str],
    explanation_query: str | None = None,
    provider: str | None = None,
    model: str | None = None,
) -> WorkflowResult:
    """Generation-fenced ORIENT evidence check: resolve the ready
    generation, fetch ORIENT, confirm the response actually came from
    that generation (not a race with an in-flight rebuild), assess, then
    re-verify the generation is still current before returning. The
    optional explanation phase (Stage A4) runs last, over the already
    generation-verified final assessment."""
    generation_id = await _query_generation(repo_id)
    orient_response = await fetch_orient_response(repo_id)
    if orient_response.get("ingestion_id") != generation_id:
        raise HTTPException(
            409,
            "ORIENT response generation does not match the currently ready "
            "generation; repository generation changed mid-request -- retry",
        )
    result = run_orient_workflow(orient_response, required_facets)
    await _verify_generation(repo_id, generation_id)
    return await _with_explanation("orient", result, explanation_query, provider, model)


async def run_trace_evidence(
    repo_id: str,
    start: str,
    relation_types: set[str] | None,
    direction: str,
    requested_max_depth: int,
    server_max_depth: int,
    max_nodes: int,
    required_target: str | None = None,
    explanation_query: str | None = None,
    provider: str | None = None,
    model: str | None = None,
    claim_type: ClaimType | None = None,
) -> WorkflowResult:
    """Generation-fenced TRACE evidence check. `get_cached_graph_with_
    generation` already re-checks the generation on every call (#168);
    this additionally verifies it hasn't changed again by the time the
    (synchronous, in-memory) workflow finishes, matching `hybrid_
    retrieve`'s fencing discipline for a multi-step read. The optional
    explanation phase (Stage A4) runs last, over the already generation-
    verified final assessment. `claim_type` (Stage C) is threaded
    straight through to the pure workflow -- no extra I/O, since the
    graph already loaded here carries provenance (Stage C's graph-
    transport prerequisite)."""
    generation_id = await _query_generation(repo_id)
    graph_generation_id, graph = get_cached_graph_with_generation(repo_id)
    if graph_generation_id != generation_id:
        raise HTTPException(
            409, "Repository generation changed while loading the graph; retry"
        )
    result = run_trace_workflow(
        graph,
        start,
        relation_types,
        direction,
        requested_max_depth,
        server_max_depth,
        max_nodes,
        required_target,
        claim_type,
    )
    await _verify_generation(repo_id, generation_id)
    return await _with_explanation("trace", result, explanation_query, provider, model)


async def run_impact_evidence(
    repo_id: str,
    start: str,
    max_depth: int,
    max_candidates: int,
    explanation_query: str | None = None,
    provider: str | None = None,
    model: str | None = None,
    claim_type: ClaimType | None = None,
) -> WorkflowResult:
    """Generation-fenced IMPACT evidence check -- same fencing shape as
    `run_trace_evidence`, same Stage A4 explanation phase and Stage C
    `claim_type` passthrough."""
    generation_id = await _query_generation(repo_id)
    graph_generation_id, graph = get_cached_graph_with_generation(repo_id)
    if graph_generation_id != generation_id:
        raise HTTPException(
            409, "Repository generation changed while loading the graph; retry"
        )
    result = run_impact_workflow(graph, start, max_depth, max_candidates, claim_type)
    await _verify_generation(repo_id, generation_id)
    return await _with_explanation("impact", result, explanation_query, provider, model)
