# rag_orchestrator/src/api/v1/product_investigate.py
"""
Product Investigate mode (issue #439, specs/016-product-frontend, plan step 3).

Browser-facing routes for submitting a generation-pinned investigation and
reading its run record. The agent service is behind `InvestigationBackend`
(see src/core/investigation.py); the browser never sees its address or token.

Run IDs are signed and carry their repository and generation, so a run can only
be read back through the repository and generation it was started for. There is
no caller identity yet (#438), so a run is not bound to a person.
"""

import asyncio
import logging
from typing import Literal, Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from src.api.v1 import product_routes
from src.api.v1.product_routes import ERRORS, ProductFailure, failure_response
from src.core import envelope
from src.core.config import get_settings
from src.core.envelope import EvidenceEnvelope
from src.core.investigation import (
    BackendBusy,
    BackendRefused,
    BackendUnavailable,
    CitationNotFound,
    RunFailed,
    UpstreamRun,
    get_backend,
    open_run,
    sign_run,
)

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/product", tags=["product"])

Outcome = Literal["complete", "partial", "none", "unknown"]
# "supported" is the investigation service's word for a run whose findings all
# carry verified citations; it is not a claim that the statements are proven.
_COMPLETE = {"complete", "verified_complete", "supported"}
MAX_PATH = 1024
MAX_CITATION_ID = 128
MAX_EXCERPT_CHARS = 262_144


class Capabilities(BaseModel):
    ask: bool = True
    investigate: bool


class InvestigateRequest(BaseModel):
    question: str = Field(min_length=1, max_length=2000)
    generation_id: str


class InvestigationEvidence(BaseModel):
    """A reference the run admitted. Inclusive, one-based lines; always in the
    repository and generation the run was pinned to."""

    repo_id: str
    generation_id: str
    path: str
    start_line: int
    end_line: int
    # Lets the client fetch the recorded excerpt, which stays available after
    # the repository is re-indexed.
    citation_id: Optional[str] = None


class InvestigationCitationText(BaseModel):
    """The text the investigation recorded for one citation, as stored with the
    run. It is not read from the repository now, so it may differ from the
    current source if the repository was re-indexed."""

    run_id: str
    citation_id: str
    repo_id: str
    generation_id: str
    path: str
    start_line: int
    end_line: int
    text: str
    evidence_mode: Literal["live", "fixture"] = "live"


class InvestigationFinding(BaseModel):
    statement: str
    evidence: list[InvestigationEvidence]


class ProductInvestigation(BaseModel):
    mode: Literal["investigate"] = "investigate"
    run_id: str
    repo_id: str
    generation_id: str
    status: Literal["running", "finished"]
    # `outcome` folds the service's completion into a closed set; the raw value
    # is kept in `completion_detail` so a new service value is not lost.
    outcome: Optional[Outcome] = None
    completion_detail: Optional[str] = None
    # Open string: clients must treat unknown reasons as a default case.
    stop_reason: Optional[str] = None
    evidence_mode: Literal["live", "fixture"] = "live"
    findings: list[InvestigationFinding] = Field(default_factory=list)
    open_gaps: list[str] = Field(default_factory=list)
    envelope: Optional[EvidenceEnvelope] = None


def _outcome(completion: str) -> Outcome:
    if completion in _COMPLETE:
        return "complete"
    if completion in ("partial", "none"):
        return completion  # type: ignore[return-value]
    return "unknown"


def _unavailable(message: str) -> ProductFailure:
    return ProductFailure("unavailable", 503, message)


def _stale(observed: Optional[str], when: str) -> ProductFailure:
    details = {"current_generation_id": observed} if observed else {}
    return ProductFailure(
        "stale",
        409,
        f"repository generation is not the requested generation ({when})",
        details,
    )


async def _current(repo_id: str) -> str:
    try:
        return await product_routes._current_generation(repo_id)
    except HTTPException as exc:
        raise product_routes._from_http_exception(exc) from exc


def _backend():
    backend = get_backend()
    if backend is None:
        raise _unavailable("Investigate is not enabled")
    return backend


async def _bounded(awaitable):
    """Run a backend call within the deadline and translate its failures into
    Foundry's stable errors. Nothing from the service is passed through except
    messages Foundry itself wrote."""
    seconds = get_settings().INVESTIGATE_DEADLINE_SECONDS
    try:
        return await asyncio.wait_for(awaitable, timeout=seconds)
    except BackendBusy as exc:
        raise _unavailable(
            "Another investigation is running. Try again when it finishes."
        ) from exc
    except BackendRefused as exc:
        raise _unavailable(exc.message) from exc
    except RunFailed as exc:
        raise ProductFailure(
            "unavailable",
            503,
            f"The investigation did not complete ({exc.code}).",
            {"failure_code": exc.code},
        ) from exc
    except CitationNotFound as exc:
        raise ProductFailure("not_found", 404, "citation not found") from exc
    except (BackendUnavailable, asyncio.TimeoutError) as exc:
        logger.warning("investigation service failure: %s", type(exc).__name__)
        raise _unavailable("The investigation service is unavailable") from exc


def _evidence(repo_id: str, generation_id: str, run: UpstreamRun):
    """Every returned reference must lie in the requested repository and
    generation and form a valid inclusive interval; otherwise the whole result
    is withheld (fail closed)."""
    findings = []
    for finding in run.findings:
        admitted = []
        for ref in finding.evidence:
            if ref.repo_id not in (None, repo_id) or ref.generation_id not in (
                None,
                generation_id,
            ):
                raise _unavailable("evidence fell outside the requested scope")
            if (
                not ref.path
                or len(ref.path) > MAX_PATH
                or "\x00" in ref.path
                or not 1 <= ref.start_line <= ref.end_line
            ):
                raise _unavailable("evidence carried an invalid source reference")
            cid = ref.citation_id
            if cid is not None and not (
                0 < len(cid) <= MAX_CITATION_ID and cid.isprintable()
            ):
                raise _unavailable("evidence carried an invalid citation id")
            admitted.append(
                InvestigationEvidence(
                    repo_id=repo_id,
                    generation_id=generation_id,
                    path=ref.path,
                    start_line=ref.start_line,
                    end_line=ref.end_line,
                    citation_id=cid,
                )
            )
        findings.append(
            InvestigationFinding(statement=finding.statement, evidence=admitted)
        )
    return findings


async def _record(
    run_id: str, repo_id: str, generation_id: str, run: UpstreamRun
) -> ProductInvestigation:
    if run.state == "running":
        return ProductInvestigation(
            run_id=run_id,
            repo_id=repo_id,
            generation_id=generation_id,
            status="running",
            evidence_mode=run.evidence_mode,
        )
    if run.stop_reason == "stale_generation" or (
        run.observed_generation_id and run.observed_generation_id != generation_id
    ):
        raise _stale(run.observed_generation_id, "reported by the investigation")
    findings = _evidence(repo_id, generation_id, run)
    current = await _current(repo_id)
    if current != generation_id:
        raise _stale(current, "during the run")
    outcome = _outcome(run.completion)
    notes = list(run.limitations)
    if run.stop_reason:
        notes.append(f"investigation stopped: {run.stop_reason}")
    if run.evidence_mode == "fixture":
        notes.append("synthetic fixture data, not derived from the repository")
    coverage = (
        "complete" if outcome == "complete" else ("partial" if findings else "unknown")
    )
    env = await envelope.build(repo_id, generation_id, coverage, notes)
    return ProductInvestigation(
        run_id=run_id,
        repo_id=repo_id,
        generation_id=generation_id,
        status="finished",
        outcome=outcome,
        completion_detail=run.completion,
        stop_reason=run.stop_reason,
        evidence_mode=run.evidence_mode,
        findings=findings,
        open_gaps=run.open_gaps,
        envelope=env,
    )


@router.get("/capabilities", response_model=Capabilities)
async def capabilities():
    """Which optional modes this deployment offers. The UI shows Investigate
    only when it is enabled."""
    return Capabilities(investigate=get_backend() is not None)


@router.post(
    "/repos/{repo_id}/investigations",
    response_model=ProductInvestigation,
    responses=ERRORS,
)
async def start_investigation(repo_id: str, request: InvestigateRequest):
    """Start a run pinned to the generation the user was shown. Returns at once
    with a `running` record; poll the run for its result."""
    try:
        product_routes._uuid_or_fail(
            repo_id=repo_id, generation_id=request.generation_id
        )
        backend = _backend()
        current = await _current(repo_id)
        if current != request.generation_id:
            raise _stale(current, "before the run started")
        upstream = await _bounded(
            backend.submit(repo_id, request.generation_id, request.question)
        )
        run_id = sign_run(
            get_settings().INVESTIGATE_RUN_SECRET,
            repo_id,
            request.generation_id,
            upstream,
        )
        return ProductInvestigation(
            run_id=run_id,
            repo_id=repo_id,
            generation_id=request.generation_id,
            status="running",
        )
    except ProductFailure as exc:
        return failure_response(exc)
    except Exception:
        return product_routes.unexpected_failure_response()


@router.get(
    "/repos/{repo_id}/investigations/{run_id}",
    response_model=ProductInvestigation,
    responses=ERRORS,
)
async def get_investigation(repo_id: str, run_id: str):
    try:
        product_routes._uuid_or_fail(repo_id=repo_id)
        backend = _backend()
        opened = open_run(get_settings().INVESTIGATE_RUN_SECRET, run_id)
        # A forged run and a run for another repository look the same.
        if opened is None or opened[0] != repo_id:
            raise ProductFailure("not_found", 404, "investigation not found")
        _, generation_id, upstream = opened
        run = await _bounded(backend.status(upstream))
        return await _record(run_id, repo_id, generation_id, run)
    except ProductFailure as exc:
        return failure_response(exc)
    except Exception:
        return product_routes.unexpected_failure_response()


@router.get(
    "/repos/{repo_id}/investigations/{run_id}/citations/{citation_id}",
    response_model=InvestigationCitationText,
    responses=ERRORS,
)
async def get_investigation_citation(repo_id: str, run_id: str, citation_id: str):
    """The recorded excerpt for one citation of a run. It is served from the
    run's stored record, so it is still available after a re-indexing; callers
    must label it as recorded, not as the current source."""
    try:
        product_routes._uuid_or_fail(repo_id=repo_id)
        backend = _backend()
        opened = open_run(get_settings().INVESTIGATE_RUN_SECRET, run_id)
        if opened is None or opened[0] != repo_id:
            raise ProductFailure("not_found", 404, "investigation not found")
        if not (0 < len(citation_id) <= MAX_CITATION_ID and citation_id.isprintable()):
            raise ProductFailure("invalid_request", 400, "invalid citation id")
        _, generation_id, upstream = opened
        cited = await _bounded(backend.citation(upstream, citation_id))
        if cited.repo_id != repo_id or cited.generation_id != generation_id:
            raise _unavailable("the citation fell outside the run's scope")
        if (
            not cited.path
            or len(cited.path) > MAX_PATH
            or "\x00" in cited.path
            or not 1 <= cited.start_line <= cited.end_line
            or len(cited.text) > MAX_EXCERPT_CHARS
        ):
            raise _unavailable("the citation was not valid")
        return InvestigationCitationText(
            run_id=run_id,
            citation_id=citation_id,
            repo_id=repo_id,
            generation_id=generation_id,
            path=cited.path,
            start_line=cited.start_line,
            end_line=cited.end_line,
            text=cited.text,
            evidence_mode=cited.evidence_mode,
        )
    except ProductFailure as exc:
        return failure_response(exc)
    except Exception:
        return product_routes.unexpected_failure_response()
