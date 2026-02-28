# ingestion_service/src/api/v1/repos.py

from fastapi import APIRouter
from typing import List
from pydantic import BaseModel
from datetime import datetime

from src.core import db_utils

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


@router.get("/repos", response_model=List[RepoSummary])
async def list_repos():
    """
    List all complete repositories with metadata.
    """
    repo_rows = db_utils.list_complete_repos()

    result: List[RepoSummary] = []

    for row in repo_rows:
        repo_id = str(row["repo_id"]) 
        ingestion_id = row["ingestion_id"]
        status = row["status"]
        created_at = row["created_at"]

        short_id = repo_id[:8]

        result.append(
            RepoSummary(
                id=repo_id,
                name=f"repo-{short_id}",
                display_name=f"Repository {short_id}",
                status=status,
                ingestion_id=str(ingestion_id),
                ingested_at=created_at,
                file_count=row["file_count"],
                node_count=row["node_count"],
            )
        )

    # Sort newest first
    result.sort(key=lambda r: r.ingested_at, reverse=True)

    return result