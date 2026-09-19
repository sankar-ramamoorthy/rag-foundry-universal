# api.py

from dataclasses import asdict
import logging

import httpx

from src.api.v1.models import (
    EvidenceRequest,
    EvidenceResponse,
    RAGQuery,
    RAGResponse,
    SimpleRAGQuery,
    SimpleRAGResponse,
    TraceResponse,
    ImpactResponse,
)
from src.core.config import get_settings
from src.core.evidence_service import (
    fetch_orient_response,
    run_impact_evidence,
    run_orient_evidence,
    run_trace_evidence,
)
from src.core.service import run_rag  # , search_documents
from fastapi import APIRouter, HTTPException
from src.core.simple_service import run_simple_rag  # new - no graph
from src.retrieval.evidence_workflow import WorkflowResult
from src.retrieval.trace_impact import (
    AmbiguousStart,
    assess_impact,
    resolve_start_symbol,
    traced_path,
)

router = APIRouter()

# Set up logging configuration
logging.basicConfig(level=logging.WARNING)
logger = logging.getLogger(__name__)


# /search endpoint to get vector search results without invoking the LLM
# @router.post("/search")
# async def search_endpoint(query: SearchQuery):
#    logger.debug(f"Received search query: {query}")
#
#    try:
#        # Get search results from the service layer
#        results = await search_documents(query.question, query.top_k)
#        return {"results": results}

#    except Exception as e:
#        logger.error(f"Error occurred while searching: {e}")
#        raise HTTPException(
#            status_code=500, detail="An error occurred during the search."
#        )


# /rag endpoint to run the full RAG (retrieval-augmented generation) process
@router.post("/rag", response_model=RAGResponse)
async def rag_endpoint(rag_query: RAGQuery):
    logger.debug(f"Received RAG query: {rag_query}")

    try:
        result = await run_rag(
            query=rag_query.query,
            repo_id=rag_query.repo_id,
            top_k=rag_query.top_k,
            provider=rag_query.provider,
            model=rag_query.model,
            language=rag_query.language,
            rerank=rag_query.rerank,
            claim_type=rag_query.claim_type,
        )
        return result

    except HTTPException:
        # Preserve service-layer status codes (e.g. 404 unknown repo_id)
        raise
    except Exception as e:
        logger.error(f"Error occurred during the RAG process: {e}")
        raise HTTPException(
            status_code=500,
            detail="An error occurred while processing the RAG request.",
        )


@router.get("/models")
async def list_models():
    """WP-M5: pass through the llm_service model menu so the UI can
    build its dropdown without reaching llm_service directly."""
    settings = get_settings()
    try:
        async with httpx.AsyncClient(timeout=30) as client:
            resp = await client.get(f"{settings.LLM_SERVICE_URL}/v1/models")
            resp.raise_for_status()
            return resp.json()
    except Exception as e:
        logger.error(f"Failed to fetch model menu: {e}")
        raise HTTPException(502, "llm_service model menu unavailable")


@router.get("/repos/{repo_id}/orient")
async def get_repo_orient(repo_id: str):
    """Issue #216: thin passthrough to ingestion_service's deterministic
    ORIENT endpoint (issue #197) -- no vector search, no graph expansion,
    no LLM call, entirely outside run_rag()'s retrieval path. Unlike
    /models above, this preserves ingestion_service's own 404 (no
    completed generation) and 409 (generation predates ORIENT) rather
    than collapsing every failure into one generic status: a caller
    needs to tell "this repo has no ORIENT data" apart from "ingestion_
    service is unreachable" to act correctly (e.g. re-ingest vs. retry).

    Issue #200: the fetch/error-handling itself now lives in
    `evidence_service.fetch_orient_response` (shared with the
    generation-fenced ORIENT evidence workflow); this route is purely
    the thin HTTP passthrough.
    """
    return await fetch_orient_response(repo_id)


@router.get("/repos/{repo_id}/trace", response_model=TraceResponse)
async def trace_endpoint(
    repo_id: str,
    start: str,
    relation_types: str = "CALL",
    direction: str = "forward",
    max_depth: int | None = None,
):
    """Issue #198: ordered, per-hop-evidenced path from a resolved
    starting symbol -- computed fresh from the already-cached full-repo
    graph (no vector search, no LLM, nothing persisted). Fails clearly
    (404/409/400) rather than silently truncating or guessing."""
    settings = get_settings()
    if direction not in ("forward", "reverse"):
        raise HTTPException(400, "direction must be 'forward' or 'reverse'")

    effective_depth = max_depth if max_depth is not None else settings.TRACE_MAX_DEPTH
    if effective_depth > settings.TRACE_MAX_DEPTH:
        raise HTTPException(
            400,
            f"max_depth {effective_depth} exceeds the configured cap "
            f"({settings.TRACE_MAX_DEPTH})",
        )

    from src.retrieval.codebase_utils import get_cached_graph

    graph = get_cached_graph(repo_id)
    resolved = resolve_start_symbol(graph, start)
    if resolved is None:
        raise HTTPException(404, f"No symbol resolves for start={start!r}")
    if isinstance(resolved, AmbiguousStart):
        raise HTTPException(
            409,
            f"start={start!r} is ambiguous; matching canonical_ids: "
            f"{resolved.candidates}",
        )

    result = traced_path(
        graph,
        resolved.canonical_id,
        relation_types={r.strip() for r in relation_types.split(",") if r.strip()},
        direction=direction,
        max_depth=effective_depth,
        max_nodes=settings.TRACE_MAX_NODES,
    )
    return TraceResponse(repo_id=repo_id, **asdict(result))


@router.get("/repos/{repo_id}/impact", response_model=ImpactResponse)
async def impact_endpoint(repo_id: str, start: str, max_depth: int | None = None):
    """Issue #198: candidate-affected-set (reverse CALL/IMPORTS/INHERITS/
    OVERRIDES) from a resolved starting symbol -- a candidate set, not a
    guarantee of breakage. Same fail-clearly bar as /trace."""
    settings = get_settings()
    effective_depth = max_depth if max_depth is not None else settings.IMPACT_MAX_DEPTH
    if effective_depth > settings.IMPACT_MAX_DEPTH:
        raise HTTPException(
            400,
            f"max_depth {effective_depth} exceeds the configured cap "
            f"({settings.IMPACT_MAX_DEPTH})",
        )

    from src.retrieval.codebase_utils import get_cached_graph

    graph = get_cached_graph(repo_id)
    resolved = resolve_start_symbol(graph, start)
    if resolved is None:
        raise HTTPException(404, f"No symbol resolves for start={start!r}")
    if isinstance(resolved, AmbiguousStart):
        raise HTTPException(
            409,
            f"start={start!r} is ambiguous; matching canonical_ids: "
            f"{resolved.candidates}",
        )

    result = assess_impact(
        graph,
        resolved.canonical_id,
        max_depth=effective_depth,
        max_candidates=settings.IMPACT_MAX_CANDIDATES,
    )
    return ImpactResponse(repo_id=repo_id, **asdict(result))


@router.post("/rag/simple", response_model=SimpleRAGResponse)
async def simple_rag_endpoint(simple_rag_query: SimpleRAGQuery):
    """Simple RAG for regular documents - no graph traversal."""
    logger.debug(f"Received RAG query: {simple_rag_query}")

    try:
        result = await run_simple_rag(
            query=simple_rag_query.query,
            top_k=simple_rag_query.top_k,
            provider=simple_rag_query.provider,
            model=simple_rag_query.model,
            rerank=simple_rag_query.rerank,
        )
        return result

    except Exception as e:
        logger.error(f"Error occurred during the RAG process: {e}")
        raise HTTPException(
            status_code=500,
            detail="An error occurred while processing the RAG request.",
        )


# --- Issue #200, Stage A3: bounded evidence-sufficiency workflow ---


def _to_evidence_response(
    repo_id: str, mode: str, result: WorkflowResult
) -> EvidenceResponse:
    return EvidenceResponse(repo_id=repo_id, mode=mode, **asdict(result))


async def _dispatch_orient_evidence(
    repo_id: str, req: EvidenceRequest
) -> WorkflowResult:
    if req.start or req.relation_types or req.required_target:
        raise HTTPException(
            400, "mode=orient does not accept start/relation_types/required_target"
        )
    return await run_orient_evidence(
        repo_id,
        req.required_facets or [],
        explanation_query=req.explanation_query,
        provider=req.provider,
        model=req.model,
    )


async def _dispatch_trace_evidence(
    repo_id: str, req: EvidenceRequest
) -> WorkflowResult:
    if not req.start:
        raise HTTPException(400, "mode=trace requires start")
    if req.direction not in ("forward", "reverse"):
        raise HTTPException(400, "direction must be 'forward' or 'reverse'")
    if req.required_facets:
        raise HTTPException(400, "mode=trace does not accept required_facets")

    settings = get_settings()
    requested_depth = (
        req.max_depth if req.max_depth is not None else settings.TRACE_MAX_DEPTH
    )
    if not 1 <= requested_depth <= settings.TRACE_MAX_DEPTH:
        raise HTTPException(
            400, f"max_depth must be between 1 and {settings.TRACE_MAX_DEPTH}"
        )
    relation_types = (
        {r.strip() for r in req.relation_types if r.strip()}
        if req.relation_types
        else {"CALL"}
    )
    return await run_trace_evidence(
        repo_id,
        req.start,
        relation_types,
        req.direction,
        requested_depth,
        settings.TRACE_MAX_DEPTH,
        settings.TRACE_MAX_NODES,
        req.required_target,
        explanation_query=req.explanation_query,
        provider=req.provider,
        model=req.model,
    )


async def _dispatch_impact_evidence(
    repo_id: str, req: EvidenceRequest
) -> WorkflowResult:
    if not req.start:
        raise HTTPException(400, "mode=impact requires start")
    if req.relation_types or req.required_target or req.required_facets:
        raise HTTPException(
            400,
            "mode=impact does not accept relation_types/required_target/"
            "required_facets",
        )
    if req.direction != "forward":
        raise HTTPException(400, "mode=impact does not accept a direction override")

    settings = get_settings()
    requested_depth = (
        req.max_depth if req.max_depth is not None else settings.IMPACT_MAX_DEPTH
    )
    if not 1 <= requested_depth <= settings.IMPACT_MAX_DEPTH:
        raise HTTPException(
            400, f"max_depth must be between 1 and {settings.IMPACT_MAX_DEPTH}"
        )
    return await run_impact_evidence(
        repo_id,
        req.start,
        requested_depth,
        settings.IMPACT_MAX_CANDIDATES,
        explanation_query=req.explanation_query,
        provider=req.provider,
        model=req.model,
    )


_EVIDENCE_DISPATCH = {
    "orient": _dispatch_orient_evidence,
    "trace": _dispatch_trace_evidence,
    "impact": _dispatch_impact_evidence,
}


@router.post("/repos/{repo_id}/evidence", response_model=EvidenceResponse)
async def evidence_endpoint(repo_id: str, req: EvidenceRequest):
    """Issue #200 (Stage A3): bounded evidence-sufficiency workflow --
    initial mode computation, mechanical obligation assessment (Stage
    A1), and at most one bounded repair (Stage A2), generation-fenced
    throughout (`evidence_service.py`). Read-only: no writes, no LLM
    call, no generated answer (that's Stage A4).

    A missing/ambiguous start or an unmet obligation is a normal
    *result* -- `status="partial"`/`"needs_clarification"` in the
    response body -- not an HTTP error. Only infra/lifecycle failures
    (repository not ready, generation changed mid-request, ingestion_
    service unreachable) raise.
    """
    dispatch = _EVIDENCE_DISPATCH[req.mode]  # pydantic Literal already restricts this
    result = await dispatch(repo_id, req)
    return _to_evidence_response(repo_id, req.mode, result)
