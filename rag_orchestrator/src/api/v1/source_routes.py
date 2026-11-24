# rag_orchestrator/src/api/v1/source_routes.py
"""
Source read and locate through the orchestrator (issue #408,
specs/013-orchestrator-read-and-locate).

Thin, read-only routes over the ingestion service's source navigation API and
the verified Python inventory in `execution_policy`. No new storage and no
model call. Every successful body keeps the ingestion fields unchanged and
adds the evidence envelope.
"""

import hashlib
import logging
from typing import Any, Optional
from uuid import UUID

import httpx
from fastapi import APIRouter, HTTPException
from fastapi.responses import JSONResponse
from pydantic import ValidationError

from src.core import envelope, execution_policy, service
from src.core.config import get_settings

logger = logging.getLogger(__name__)
router = APIRouter()

PYTHON_DOC_TYPE = "python source"
MAX_DEFINITION_FILES = 5
GLOB_CHARS = set("*?")
LOCATE_LIMITATION = (
    "locate matches paths only; definition-name and semantic search are not included"
)


async def _generation(repo_id: str, generation_id: Optional[str]) -> str:
    return generation_id or await service._query_generation(repo_id)


async def _ingestion_get(repo_id: str, suffix: str, params: dict[str, Any]):
    url = f"{get_settings().INGESTION_SERVICE_URL}/v1/repos/{repo_id}/source/{suffix}"
    clean = {k: v for k, v in params.items() if v is not None}
    try:
        async with httpx.AsyncClient(timeout=30) as client:
            return await client.get(url, params=clean)
    except httpx.HTTPError as exc:
        logger.error("ingestion_service unreachable for source %s: %s", suffix, exc)
        raise HTTPException(502, "ingestion_service unavailable") from exc


def _passthrough_error(response: httpx.Response) -> JSONResponse:
    try:
        body = response.json()
    except ValueError:
        body = {"error_code": "SOURCE_UNAVAILABLE", "message": response.text[:200]}
    return JSONResponse(body, status_code=response.status_code)


@router.get("/repos/{repo_id}/source/files")
async def source_files(
    repo_id: str,
    generation_id: Optional[str] = None,
    pattern: str = "**",
    limit: int = 50,
    cursor: Optional[str] = None,
):
    generation = await _generation(repo_id, generation_id)
    response = await _ingestion_get(
        repo_id,
        "files",
        {
            "generation_id": generation,
            "pattern": pattern,
            "limit": limit,
            "cursor": cursor,
        },
    )
    if response.is_error:
        return _passthrough_error(response)
    body = response.json()
    more = body.get("next_cursor") is not None
    env = await envelope.build(
        repo_id,
        body.get("generation_id"),
        "partial" if more else "complete",
        ["more pages available; pass next_cursor"] if more else [],
        commit_sha=body.get("commit_sha"),
        commit_known=True,
    )
    return {**body, "envelope": env.model_dump()}


@router.get("/repos/{repo_id}/source/read")
async def source_read(
    repo_id: str,
    path: str,
    generation_id: Optional[str] = None,
    start_line: Optional[int] = None,
    end_line: Optional[int] = None,
):
    generation = await _generation(repo_id, generation_id)
    response = await _ingestion_get(
        repo_id,
        "read",
        {
            "generation_id": generation,
            "path": path,
            "start_line": start_line,
            "end_line": end_line,
        },
    )
    if response.is_error:
        return _passthrough_error(response)
    body = response.json()
    text = body.get("text")
    if not isinstance(text, str):
        raise HTTPException(502, "source read returned no text")
    digest = hashlib.sha256(text.encode()).hexdigest()
    if digest != body.get("returned_text_sha256"):
        raise HTTPException(502, "source read digest does not match returned text")
    following = body.get("next_start_line")
    env = await envelope.build(
        repo_id,
        body.get("generation_id"),
        "partial" if following is not None else "complete",
        [f"file continues at line {following}"] if following is not None else [],
        commit_sha=body.get("commit_sha"),
        commit_known=True,
    )
    return {**body, "envelope": env.model_dump()}


def _match_kind(query: str) -> tuple[str, str]:
    """Return (glob pattern, match kind) for a path, glob or basename."""
    if "/" in query or GLOB_CHARS & set(query):
        return query, "glob"
    return f"**/{query}", "basename"


async def _definitions(repo_id: str, generation: str, path: str, query: str):
    request = execution_policy.Request(
        repo_id=UUID(repo_id),
        generation_id=UUID(generation),
        question=f"locate {query}"[:8192],
        family="python_inventory",
        path=path,
        maximum_strategy="deterministic",
    )
    result = await execution_policy.run_execution_policy(request)
    if result["completion"] == "verified_complete":
        rows = [
            {
                "name": r["name"],
                "start_line": r["start"],
                "end_line": r["end"],
                "kind": r["kind"],
            }
            for r in result["inventory"]
        ]
        return rows, "verified_complete", result["returned_text_sha256"]
    return None, result["termination_reason"], None


async def _fill_definitions(
    entry: dict[str, Any],
    attempt: bool,
    repo_id: str,
    generation: str,
    query: str,
    doc_type: str,
) -> list[str]:
    """Set one candidate's definitions and status; return limitation notes.
    Absence of coverage is reported, never shown as an empty result."""
    path = entry["path"]
    if not attempt:
        if doc_type != PYTHON_DOC_TYPE:
            entry["definitions_status"] = "not_covered_language"
            return [f"definitions not covered for {doc_type}: {path}"]
        entry["definitions_status"] = "not_attempted"
        cap = MAX_DEFINITION_FILES
        return [f"definitions not attempted beyond {cap} files: {path}"]
    try:
        rows, status, digest = await _definitions(repo_id, generation, path, query)
    except (ValidationError, ValueError):
        rows, status, digest = None, "invalid_request", None
    entry.update(
        definitions=rows, definitions_status=status, returned_text_sha256=digest
    )
    if status == "verified_complete":
        return []
    return [f"definitions not verified for {path}"]


@router.get("/repos/{repo_id}/locate")
async def locate(
    repo_id: str,
    query: str,
    generation_id: Optional[str] = None,
    limit: int = 20,
    include_definitions: bool = True,
    cursor: Optional[str] = None,
):
    try:
        UUID(repo_id)
        if generation_id:
            UUID(generation_id)
    except ValueError as exc:
        raise HTTPException(400, "repo_id and generation_id must be UUIDs") from exc
    if not 1 <= limit <= 50:
        raise HTTPException(400, "limit must be between 1 and 50")
    generation = await _generation(repo_id, generation_id)
    pattern, kind = _match_kind(query)
    response = await _ingestion_get(
        repo_id,
        "files",
        {
            "generation_id": generation,
            "pattern": pattern,
            "limit": limit,
            "cursor": cursor,
        },
    )
    if response.is_error:
        return _passthrough_error(response)
    files = response.json()
    limitations = [LOCATE_LIMITATION]
    complete = files.get("next_cursor") is None
    if not complete:
        limitations.append("more matching files exist than this page returned")
    if not files["files"]:
        limitations.append(f"no file matched {pattern!r} at this generation")

    candidates = []
    python_attempted = 0
    for item in files["files"]:
        entry = {
            "path": item["path"],
            "canonical_id": item["canonical_id"],
            "doc_type": item["doc_type"],
            "source_status": item["source_status"],
            "match": kind,
            "definitions": None,
            "definitions_status": "not_requested",
            "returned_text_sha256": None,
        }
        if include_definitions:
            attempt = item["doc_type"] == PYTHON_DOC_TYPE
            attempt = attempt and python_attempted < MAX_DEFINITION_FILES
            python_attempted += attempt
            limitations.extend(
                await _fill_definitions(
                    entry, attempt, repo_id, generation, query, item["doc_type"]
                )
            )
        candidates.append(entry)

    verified = all(
        c["definitions_status"] in ("verified_complete", "not_requested")
        for c in candidates
    )
    env = await envelope.build(
        repo_id,
        files.get("generation_id"),
        "complete" if complete and verified and candidates else "partial",
        limitations,
        commit_sha=files.get("commit_sha"),
        commit_known=True,
    )
    return {
        "repo_id": repo_id,
        "generation_id": files.get("generation_id"),
        "query": query,
        "pattern": pattern,
        "candidates": candidates,
        "next_cursor": files.get("next_cursor"),
        "envelope": env.model_dump(),
    }
