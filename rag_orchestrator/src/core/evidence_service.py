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

import httpx
from fastapi import HTTPException

from src.core.config import get_settings
from src.core.service import _query_generation, _verify_generation
from src.retrieval.codebase_utils import get_cached_graph_with_generation
from src.retrieval.evidence_workflow import (
    WorkflowResult,
    run_impact_workflow,
    run_orient_workflow,
    run_trace_workflow,
)

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


async def run_orient_evidence(
    repo_id: str, required_facets: list[str]
) -> WorkflowResult:
    """Generation-fenced ORIENT evidence check: resolve the ready
    generation, fetch ORIENT, confirm the response actually came from
    that generation (not a race with an in-flight rebuild), assess, then
    re-verify the generation is still current before returning."""
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
    return result


async def run_trace_evidence(
    repo_id: str,
    start: str,
    relation_types: set[str] | None,
    direction: str,
    requested_max_depth: int,
    server_max_depth: int,
    max_nodes: int,
    required_target: str | None = None,
) -> WorkflowResult:
    """Generation-fenced TRACE evidence check. `get_cached_graph_with_
    generation` already re-checks the generation on every call (#168);
    this additionally verifies it hasn't changed again by the time the
    (synchronous, in-memory) workflow finishes, matching `hybrid_
    retrieve`'s fencing discipline for a multi-step read."""
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
    )
    await _verify_generation(repo_id, generation_id)
    return result


async def run_impact_evidence(
    repo_id: str,
    start: str,
    max_depth: int,
    max_candidates: int,
) -> WorkflowResult:
    """Generation-fenced IMPACT evidence check -- same fencing shape as
    `run_trace_evidence`."""
    generation_id = await _query_generation(repo_id)
    graph_generation_id, graph = get_cached_graph_with_generation(repo_id)
    if graph_generation_id != generation_id:
        raise HTTPException(
            409, "Repository generation changed while loading the graph; retry"
        )
    result = run_impact_workflow(graph, start, max_depth, max_candidates)
    await _verify_generation(repo_id, generation_id)
    return result
