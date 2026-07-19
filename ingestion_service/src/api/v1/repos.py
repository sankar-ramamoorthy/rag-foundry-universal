# ingestion_service/src/api/v1/repos.py

from fastapi import APIRouter
from typing import List, Optional
from pydantic import BaseModel
from datetime import datetime

from src.core import db_utils
from src.core.repo_naming import derive_repo_identity

#router = APIRouter(prefix="/v1", tags=["repos"])
router = APIRouter(tags=["repos"])


class RepoSummary(BaseModel):
    id: str
    name: str
    display_name: str
    status: str
    ingestion_id: str
    ingested_at: datetime
    file_count: int
    node_count: int
    source_type: Optional[str] = None
    git_url: Optional[str] = None
    local_path: Optional[str] = None
    branch: Optional[str] = None


def build_repo_summary(row: dict) -> RepoSummary:
    """
    Map one list_complete_repos() row to a RepoSummary, deriving real
    names from ingestion metadata (issue #30 Part 5). UUID-derived labels
    remain only as last-resort fallback for rows without usable metadata.
    """
    repo_id = str(row["repo_id"])
    short_id = repo_id[:8]

    identity = derive_repo_identity(row.get("ingestion_metadata"))

    return RepoSummary(
        id=repo_id,
        name=identity["name"] or f"repo-{short_id}",
        display_name=identity["display_name"] or f"Repository {short_id}",
        status=row["status"],
        ingestion_id=str(row["ingestion_id"]),
        ingested_at=row["created_at"],
        file_count=row["file_count"],
        node_count=row["node_count"],
        source_type=identity["source_type"],
        git_url=identity["git_url"],
        local_path=identity["local_path"],
        branch=identity["branch"],
    )


@router.get("/repos", response_model=List[RepoSummary])
async def list_repos():
    """
    List all complete repositories with metadata.
    """
    repo_rows = db_utils.list_complete_repos()

    result = [build_repo_summary(row) for row in repo_rows]

    # Sort newest first
    result.sort(key=lambda r: r.ingested_at, reverse=True)

    return result
