# rag_orchestrator/src/api/v1/product_routes.py
"""
Browser-facing product API, read side (issue #432, specs/016-product-frontend).

Additive routes under `/v1/product`. They reuse the behavior of the existing
orchestrator routes (which keep their contracts) and add what a browser needs:

- a sanitized repository list (no local paths, no repository URLs),
- a readiness lookup,
- typed response models for Orient, files, Locate and source read,
- every route pinned to a caller-supplied `generation_id`, and
- one stable error body, `ProductError`, with a closed set of codes.

No new storage and no model call.
"""

import json
import logging
from datetime import datetime
from typing import Any, Literal, Optional
from uuid import UUID, uuid4

import httpx
from fastapi import APIRouter, HTTPException
from fastapi.responses import JSONResponse
from pydantic import BaseModel, ConfigDict, Field

from src.api.v1 import source_routes
from src.api.v1.models import RAGQuery, RAGResponse
from src.core import envelope
from src.core import service
from src.core.citations import Citation
from src.core.config import get_settings
from src.core.envelope import EvidenceEnvelope
from src.core.evidence_service import fetch_orient_response

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/product", tags=["product"])

ErrorCode = Literal[
    "unavailable",
    "stale",
    "invalid_range",
    "resource_limit",
    "not_found",
    "invalid_request",
]

# Ingestion source-navigation `error_code` -> (product code, HTTP status).
_INGESTION_CODES: dict[str, tuple[ErrorCode, int]] = {
    "GENERATION_MISMATCH": ("stale", 409),
    "GENERATION_UNAVAILABLE": ("unavailable", 503),
    "SOURCE_UNAVAILABLE": ("unavailable", 503),
    "INCONSISTENT_SOURCE": ("unavailable", 503),
    "REPOSITORY_NOT_FOUND": ("not_found", 404),
    "FILE_NOT_FOUND": ("not_found", 404),
    "AMBIGUOUS_PATH": ("invalid_request", 400),
    "INVALID_REQUEST": ("invalid_request", 400),
    "INVALID_LINE_RANGE": ("invalid_range", 416),
    "READ_TOO_LARGE": ("resource_limit", 413),
    "RESPONSE_TOO_LARGE": ("resource_limit", 413),
    "SCAN_LIMIT_EXCEEDED": ("resource_limit", 413),
    "DEADLINE_EXCEEDED": ("resource_limit", 503),
}
_HTTP_CODES: dict[int, tuple[ErrorCode, int]] = {
    400: ("invalid_request", 400),
    404: ("not_found", 404),
    409: ("stale", 409),
    413: ("resource_limit", 413),
    416: ("invalid_range", 416),
}


class ProductError(BaseModel):
    code: ErrorCode
    message: str
    details: dict[str, Any] = Field(default_factory=dict)


class ProductErrorResponse(BaseModel):
    error: ProductError


class ProductFailure(Exception):
    def __init__(
        self,
        code: ErrorCode,
        status: int,
        message: str,
        details: Optional[dict[str, Any]] = None,
    ):
        super().__init__(message)
        self.code, self.status = code, status
        self.message, self.details = message, details or {}


def failure_response(exc: ProductFailure) -> JSONResponse:
    body = ProductErrorResponse(
        error=ProductError(code=exc.code, message=exc.message, details=exc.details)
    )
    return JSONResponse(body.model_dump(), status_code=exc.status)


def unexpected_failure_response() -> JSONResponse:
    """Any failure a route did not anticipate still answers with the stable
    error body, never a bare 500 and never exception text."""
    logger.exception("unexpected failure in a product route")
    return failure_response(
        ProductFailure("unavailable", 503, "the service could not complete the request")
    )


def _from_ingestion_body(status: int, body: Any) -> ProductFailure:
    if isinstance(body, dict) and "error_code" in body:
        code, http = _INGESTION_CODES.get(str(body["error_code"]), ("unavailable", 503))
        details = body.get("details")
        return ProductFailure(
            code,
            http,
            str(body.get("message") or "request failed")[:200],
            details if isinstance(details, dict) else {},
        )
    code, http = _HTTP_CODES.get(status, ("unavailable", 503))
    return ProductFailure(code, http, "request failed")


def _from_http_exception(exc: HTTPException) -> ProductFailure:
    code, http = _HTTP_CODES.get(exc.status_code, ("unavailable", 503))
    detail = exc.detail if isinstance(exc.detail, str) else "request failed"
    return ProductFailure(code, http, detail[:200])


async def _unwrap(awaitable) -> dict[str, Any]:
    """Run an existing orchestrator handler and normalize its failures."""
    try:
        result = await awaitable
    except HTTPException as exc:
        raise _from_http_exception(exc) from exc
    if isinstance(result, JSONResponse):
        try:
            body = json.loads(result.body)
        except ValueError:
            body = None
        raise _from_ingestion_body(result.status_code, body)
    return result


def _uuid_or_fail(**values: Optional[str]) -> None:
    for name, value in values.items():
        try:
            UUID(str(value))
        except ValueError as exc:
            raise ProductFailure(
                "invalid_request", 400, f"{name} must be a UUID"
            ) from exc


ERRORS: dict[int | str, dict[str, Any]] = {
    status: {"model": ProductErrorResponse} for status in (400, 404, 409, 413, 416, 503)
}


# --- repositories ---


class ProductRepo(BaseModel):
    """The only repository fields a browser sees. No paths, no URLs."""

    repo_id: str
    name: str
    display_name: str
    source_type: Optional[str] = None
    branch: Optional[str] = None
    ingested_at: Optional[datetime] = None
    file_count: int
    node_count: int


class ProductRepoList(BaseModel):
    repos: list[ProductRepo]


class Readiness(BaseModel):
    repo_id: str
    status: Literal["ready"]
    generation_id: str
    commit_sha: Optional[str] = None
    ingested_at: Optional[datetime] = None
    is_incremental: bool = False


async def _ingestion_json(path: str) -> Any:
    url = f"{get_settings().INGESTION_SERVICE_URL}{path}"
    try:
        async with httpx.AsyncClient(timeout=30) as client:
            response = await client.get(url)
    except httpx.HTTPError as exc:
        logger.error("ingestion_service unreachable for %s: %s", path, exc)
        raise ProductFailure(
            "unavailable", 503, "repository service unavailable"
        ) from exc
    if response.is_error:
        try:
            body = response.json()
        except ValueError:
            body = None
        raise _from_ingestion_body(response.status_code, body)
    return response.json()


@router.get("/repos", response_model=ProductRepoList, responses=ERRORS)
async def list_repos():
    try:
        rows = await _ingestion_json("/v1/repos")
        return ProductRepoList(
            repos=[
                ProductRepo(
                    repo_id=row["id"],
                    name=row["name"],
                    display_name=row["display_name"],
                    source_type=row.get("source_type"),
                    branch=row.get("branch"),
                    ingested_at=row.get("ingested_at"),
                    file_count=row["file_count"],
                    node_count=row["node_count"],
                )
                for row in rows
            ]
        )
    except ProductFailure as exc:
        return failure_response(exc)
    except Exception:
        return unexpected_failure_response()


@router.get("/repos/{repo_id}/readiness", response_model=Readiness, responses=ERRORS)
async def readiness(repo_id: str):
    try:
        _uuid_or_fail(repo_id=repo_id)
        data = await _ingestion_json(f"/v1/repos/{repo_id}/generation")
        if data.get("generation_status") != "ready" or not data.get("ingestion_id"):
            raise ProductFailure(
                "unavailable",
                503,
                "repository has no ready generation",
                {"generation_status": str(data.get("generation_status"))},
            )
        return Readiness(
            repo_id=repo_id,
            status="ready",
            generation_id=data["ingestion_id"],
            commit_sha=data.get("commit_sha") or None,
            ingested_at=data.get("ingested_at"),
            is_incremental=bool(data.get("is_incremental")),
        )
    except ProductFailure as exc:
        return failure_response(exc)
    except Exception:
        return unexpected_failure_response()


# --- orient ---


class OrientManifest(BaseModel):
    kind: str
    path: str


class OrientService(BaseModel):
    name: str
    compose_file: str
    dockerfile: Optional[str] = None
    container_name: Optional[str] = None
    entry_point: Optional[str] = None
    entry_point_source: Optional[str] = None


class OrientGap(BaseModel):
    category: str
    path: Optional[str] = None
    reason: str


class ProductOrient(BaseModel):
    repo_id: str
    generation_id: str
    commit_sha: Optional[str] = None
    languages: dict[str, int]
    file_counts: dict[str, int]
    manifests: list[OrientManifest]
    services: list[OrientService]
    test_dirs: list[str]
    docs_dirs: list[str]
    heuristic_fields: list[str]
    gaps: list[OrientGap]
    envelope: EvidenceEnvelope


@router.get("/repos/{repo_id}/orient", response_model=ProductOrient, responses=ERRORS)
async def orient(repo_id: str, generation_id: str):
    try:
        _uuid_or_fail(repo_id=repo_id, generation_id=generation_id)
        body = await _unwrap(fetch_orient_response(repo_id))
        if body.get("ingestion_id") != generation_id:
            raise ProductFailure(
                "stale",
                409,
                "repository generation is not the requested generation",
                {"current_generation_id": str(body.get("ingestion_id"))},
            )
        coverage, notes = envelope.orient_coverage(
            body.get("gaps") or [], body.get("heuristic_fields") or []
        )
        env = await envelope.build(
            repo_id,
            body.get("ingestion_id"),
            coverage,
            notes,
            commit_sha=body.get("commit_sha"),
            commit_known=True,
        )
        return ProductOrient(
            repo_id=repo_id,
            generation_id=generation_id,
            commit_sha=body.get("commit_sha"),
            languages=body["languages"],
            file_counts=body["file_counts"],
            manifests=body["manifests"],
            services=body["services"],
            test_dirs=body["test_dirs"],
            docs_dirs=body["docs_dirs"],
            heuristic_fields=body["heuristic_fields"],
            gaps=body["gaps"],
            envelope=env,
        )
    except ProductFailure as exc:
        return failure_response(exc)
    except Exception:
        return unexpected_failure_response()


# --- files, locate, source ---


class ProductFile(BaseModel):
    path: str
    canonical_id: str
    document_id: str
    doc_type: str
    source_status: Literal["available", "unavailable"]


class ProductFiles(BaseModel):
    repo_id: str
    generation_id: str
    commit_sha: Optional[str] = None
    files: list[ProductFile]
    next_cursor: Optional[str] = None
    envelope: EvidenceEnvelope


@router.get("/repos/{repo_id}/files", response_model=ProductFiles, responses=ERRORS)
async def files(
    repo_id: str,
    generation_id: str,
    pattern: str = "**",
    limit: int = 50,
    cursor: Optional[str] = None,
):
    try:
        _uuid_or_fail(repo_id=repo_id, generation_id=generation_id)
        body = await _unwrap(
            source_routes.source_files(repo_id, generation_id, pattern, limit, cursor)
        )
        return ProductFiles(**body)
    except ProductFailure as exc:
        return failure_response(exc)
    except Exception:
        return unexpected_failure_response()


class LocateDefinition(BaseModel):
    name: str
    start_line: int
    end_line: int
    kind: str


class LocateCandidate(BaseModel):
    path: str
    canonical_id: str
    doc_type: str
    source_status: str
    match: Literal["glob", "basename"]
    definitions: Optional[list[LocateDefinition]] = None
    definitions_status: str
    returned_text_sha256: Optional[str] = None


class ProductLocate(BaseModel):
    repo_id: str
    generation_id: str
    query: str
    pattern: str
    candidates: list[LocateCandidate]
    next_cursor: Optional[str] = None
    envelope: EvidenceEnvelope


@router.get("/repos/{repo_id}/locate", response_model=ProductLocate, responses=ERRORS)
async def locate(
    repo_id: str,
    generation_id: str,
    query: str,
    limit: int = 20,
    include_definitions: bool = True,
):
    try:
        _uuid_or_fail(repo_id=repo_id, generation_id=generation_id)
        body = await _unwrap(
            source_routes.locate(
                repo_id, query, generation_id, limit, include_definitions
            )
        )
        return ProductLocate(**body)
    except ProductFailure as exc:
        return failure_response(exc)
    except Exception:
        return unexpected_failure_response()


class ProductSource(BaseModel):
    """Inclusive, one-based lines. `start_line`/`end_line` are the effective
    range actually returned; `complete_file` says whether it is the whole file."""

    model_config = ConfigDict(extra="ignore")

    repo_id: str
    generation_id: str
    commit_sha: Optional[str] = None
    path: str
    canonical_id: str
    document_id: str
    doc_type: str
    representation: Literal["stored_source"]
    start_line: int
    end_line: int
    complete_file: bool
    next_start_line: Optional[int] = None
    text: str
    returned_text_sha256: str
    text_sha256: Optional[str] = None
    total_lines: Optional[int] = None
    envelope: EvidenceEnvelope


@router.get("/repos/{repo_id}/source", response_model=ProductSource, responses=ERRORS)
async def source(
    repo_id: str,
    generation_id: str,
    path: str,
    start_line: Optional[int] = None,
    end_line: Optional[int] = None,
):
    try:
        _uuid_or_fail(repo_id=repo_id, generation_id=generation_id)
        if (start_line is not None and start_line < 1) or (
            end_line is not None
            and (end_line < 1 or (start_line is not None and end_line < start_line))
        ):
            raise ProductFailure(
                "invalid_range",
                416,
                "lines are one-based and start must not exceed end",
            )
        body = await _unwrap(
            source_routes.source_read(
                repo_id, path, generation_id, start_line, end_line
            )
        )
        return ProductSource(**body)
    except ProductFailure as exc:
        return failure_response(exc)
    except Exception:
        return unexpected_failure_response()


# --- ask (issue #433) ---


class AskRequest(BaseModel):
    question: str = Field(min_length=1, max_length=8192)
    generation_id: str
    top_k: int = Field(default=5, ge=1, le=20)
    provider: Optional[str] = None
    model: Optional[str] = None


class ProductAsk(BaseModel):
    mode: Literal["ask"] = "ask"
    run_id: str
    repo_id: str
    generation_id: str
    question: str
    answer: str
    sources: list[str]
    model_used: Optional[str] = None
    trace_id: Optional[str] = None
    envelope: EvidenceEnvelope
    citations: list[Citation]


async def _current_generation(repo_id: str) -> str:
    return await service._query_generation(repo_id)


async def _run_standard_rag(query: RAGQuery) -> RAGResponse:
    # Imported here: routes.py is the owner of the standard RAG wiring.
    from src.api.v1 import routes

    result = await routes.rag_endpoint(query)
    # The pipeline returns its own result model (RAGResult); FastAPI only turns
    # it into RAGResponse through response_model on the legacy route. Coerce it
    # here so a caller never depends on that.
    return RAGResponse.model_validate(result.model_dump())


def _stale(expected: str, current: str, when: str) -> ProductFailure:
    return ProductFailure(
        "stale",
        409,
        f"repository generation is not the requested generation ({when})",
        {"current_generation_id": current},
    )


@router.post("/repos/{repo_id}/ask", response_model=ProductAsk, responses=ERRORS)
async def ask(repo_id: str, request: AskRequest):
    """Standard Foundry RAG pinned to one generation.

    The generation is verified before any retrieval or generation call, and
    again before the result is returned. A result is never published against
    a generation other than the one requested.
    """
    try:
        _uuid_or_fail(repo_id=repo_id, generation_id=request.generation_id)
        try:
            current = await _current_generation(repo_id)
        except HTTPException as exc:
            raise _from_http_exception(exc) from exc
        if current != request.generation_id:
            raise _stale(request.generation_id, current, "before dispatch")

        try:
            result = await _run_standard_rag(
                RAGQuery(
                    query=request.question,
                    repo_id=repo_id,
                    execution_mode="rag",
                    top_k=request.top_k,
                    provider=request.provider,
                    model=request.model,
                )
            )
        except HTTPException as exc:
            raise _from_http_exception(exc) from exc

        env = result.envelope
        if env is None or env.generation_id != request.generation_id:
            raise _stale(
                request.generation_id,
                str(env.generation_id) if env else "unknown",
                "answer was produced from another generation",
            )
        try:
            current = await _current_generation(repo_id)
        except HTTPException as exc:
            raise _from_http_exception(exc) from exc
        if current != request.generation_id:
            raise _stale(request.generation_id, current, "during answer")
        outside = [
            c
            for c in result.citations
            if c.repo_id != repo_id or c.generation_id != request.generation_id
        ]
        if outside:
            logger.error(
                "ask: %d citations outside repo/generation scope", len(outside)
            )
            raise ProductFailure(
                "unavailable", 503, "evidence fell outside the requested scope"
            )
        return ProductAsk(
            run_id=str(uuid4()),
            repo_id=repo_id,
            generation_id=request.generation_id,
            question=request.question,
            answer=result.answer,
            sources=result.sources,
            model_used=result.model_used,
            trace_id=result.trace_id,
            envelope=env,
            citations=result.citations,
        )
    except ProductFailure as exc:
        return failure_response(exc)
    except Exception:
        return unexpected_failure_response()
