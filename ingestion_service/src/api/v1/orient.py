# ingestion_service/src/api/v1/orient.py
"""
GET /v1/repos/{repo_id}/orient -- issue #197 (ORIENT).

A deterministic repository-overview query: given a repo_id, returns
services/packages/manifests/languages/entry points read directly from
facts computed once during ingestion (structural_inventory.py), not
via top-k similarity search or an LLM call. Same generation always
returns the same JSON.
"""

import logging
from datetime import datetime
from typing import List, Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from src.core import db_utils

router = APIRouter(tags=["orient"])
logger = logging.getLogger(__name__)


class ManifestEntry(BaseModel):
    kind: str
    path: str


class ServiceEntry(BaseModel):
    name: str
    compose_file: str
    dockerfile: Optional[str] = None
    container_name: Optional[str] = None
    entry_point: Optional[str] = None
    entry_point_source: Optional[str] = None


class GapNoteModel(BaseModel):
    category: str
    path: Optional[str] = None
    reason: str


class OrientResponse(BaseModel):
    repo_id: str
    ingestion_id: str
    generation_status: str
    commit_sha: Optional[str] = None
    languages: dict[str, int]
    file_counts: dict[str, int]
    manifests: List[ManifestEntry]
    services: List[ServiceEntry]
    test_dirs: List[str]
    docs_dirs: List[str]
    heuristic_fields: List[str]
    gaps: List[GapNoteModel]
    computed_at: Optional[datetime] = None


@router.get("/repos/{repo_id}/orient", response_model=OrientResponse)
async def get_repo_orient(repo_id: str):
    """
    Every field is read straight from persisted rows/JSON written once at
    ingestion time -- no recomputation, no vector search, no LLM call, no
    wall-clock "now" (computed_at is the generation's finished_at). The
    same generation always returns byte-identical JSON.
    """
    ingestion_id = db_utils.resolve_current_generation(repo_id)
    if ingestion_id is None:
        raise HTTPException(
            status_code=404,
            detail=f"No completed generation for repo_id={repo_id}",
        )

    summary = db_utils.get_structural_summary(ingestion_id)
    if summary is None:
        raise HTTPException(
            status_code=409,
            detail=(
                "This generation predates ORIENT (issue #197) -- "
                "re-ingest the repository to populate structural_summary."
            ),
        )

    status = db_utils.generation_status(repo_id)
    lineage = db_utils.generation_lineage(ingestion_id)

    return OrientResponse(
        repo_id=repo_id,
        ingestion_id=ingestion_id,
        generation_status=status,
        commit_sha=lineage.get("commit_sha"),
        computed_at=lineage.get("ingested_at"),
        **summary,
    )
