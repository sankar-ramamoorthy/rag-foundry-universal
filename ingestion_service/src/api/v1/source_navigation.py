"""#379 source navigation, isolated from the existing RAG answering path."""

import logging
from typing import Any, Literal

from fastapi import APIRouter
from fastapi.responses import JSONResponse, Response
from pydantic import BaseModel
from sqlalchemy.exc import SQLAlchemyError

from src.api.v1.models import ErrorResponse
from src.core import source_navigation as source

router = APIRouter(prefix="/repos/{repo_id}/source", tags=["source-navigation"])
logger = logging.getLogger(__name__)


class SourceFile(BaseModel):
    path: str
    canonical_id: str
    document_id: str
    doc_type: str
    source_status: Literal["available", "unavailable"]


class FilesResponse(BaseModel):
    repo_id: str
    generation_id: str
    commit_sha: str | None
    files: list[SourceFile]
    next_cursor: str | None


class ReadResponse(BaseModel):
    repo_id: str
    generation_id: str
    commit_sha: str | None
    path: str
    canonical_id: str
    document_id: str
    doc_type: str
    representation: Literal["stored_source"]
    start_line: int
    end_line: int
    complete_file: bool
    next_start_line: int | None
    text: str
    returned_text_sha256: str
    text_sha256: str | None
    total_lines: int | None


ERRORS: dict[int | str, dict[str, Any]] = {
    status: {"model": ErrorResponse} for status in (400, 404, 409, 413, 416, 422, 503)
}


def respond(operation):
    budget = source.Budget()
    try:
        body = operation(budget)
        result = Response(source.serialize(body, budget), media_type="application/json")
        budget.check()
        logger.info(
            "source navigation complete: queries=%d scanned_bytes=%d bytes=%d",
            budget.queries,
            budget.scanned,
            len(result.body),
        )
        return result
    except source.NavigationError as exc:
        logger.info(
            "source navigation failed: code=%s queries=%d scanned_bytes=%d",
            exc.body["error_code"],
            budget.queries,
            budget.scanned,
        )
        return JSONResponse(exc.body, status_code=exc.status)
    except SQLAlchemyError as exc:
        original = getattr(exc, "orig", None)
        code = getattr(original, "pgcode", None) or getattr(original, "sqlstate", None)
        timeout = code == "57014"
        return JSONResponse(
            {
                "error_code": "DEADLINE_EXCEEDED" if timeout else "SOURCE_UNAVAILABLE",
                "message": "Source read timed out"
                if timeout
                else "Source service unavailable",
                "details": {},
            },
            status_code=503,
        )


@router.get("/files", response_model=FilesResponse, responses=ERRORS)
def find_files(
    repo_id: str,
    generation_id: str,
    pattern: str = "**",
    limit: int = 50,
    cursor: str | None = None,
):
    return respond(
        lambda budget: source.find_files(
            repo_id,
            generation_id,
            pattern,
            limit,
            cursor,
            budget=budget,
        )
    )


@router.get("/read", response_model=ReadResponse, responses=ERRORS)
def read_source(
    repo_id: str,
    generation_id: str,
    path: str,
    start_line: int | None = None,
    end_line: int | None = None,
):
    return respond(
        lambda budget: source.read_source(
            repo_id,
            generation_id,
            path,
            start_line,
            end_line,
            budget=budget,
        )
    )
