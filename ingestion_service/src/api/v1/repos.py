# ingestion_service/src/api/v1/repos.py

import logging

from fastapi import APIRouter, HTTPException
from typing import List, Optional
from pydantic import BaseModel
from datetime import datetime

from src.core import db_utils
from src.core.config import get_settings
from src.core.database_session import get_engine, get_sessionmaker
from src.core.http_vectorstore import HttpVectorStore
from src.core.ingestion_ownership import RepositoryBusy, reserve_repo_mutation
from src.core.repo_naming import derive_repo_identity
from src.core.codebase.codebase_persistence import CodebaseGraphPersistence

#router = APIRouter(prefix="/v1", tags=["repos"])
router = APIRouter(tags=["repos"])
logger = logging.getLogger(__name__)
SessionLocal = get_sessionmaker()


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


class RepoDeleteResponse(BaseModel):
    status: str
    repo_id: str
    ingestion_ids: List[str]
    nodes_deleted: int
    ingestion_requests_deleted: int


@router.delete("/repos/{repo_id}", response_model=RepoDeleteResponse)
async def delete_repo(repo_id: str):
    """
    Hard-delete a repository and everything derived from it: vectors
    (every historical ingestion, not just the latest), graph nodes/
    relationships, and ingestion_requests records (issue #158).

    Idempotent: calling this on a repo_id with nothing left (already
    deleted, or never existed) returns "not_found" rather than an
    error, so a retry after a partial failure — or a duplicate call —
    is always safe to repeat.

    #166: the whole operation holds the repo-scope advisory lock so it
    cannot interleave with a concurrent ingest/rebuild of the same repo_id
    (see ingestion_ownership.reserve_ingestion, which takes the same lock
    scope for repository ingestion). A repo with an active accepted/running
    ingestion is rejected outright rather than raced against.

    Order matters and is not arbitrary (see issue #158):
      1. Enumerate every historical ingestion_id for repo_id *first*, from
         ingestion_requests.repo_id (primary, survives graph deletion) with
         a document_nodes.repo_id fallback for pre-migration rows (#166) —
         captured before step 3 deletes graph rows.
      2. Delete vectors per ingestion_id (dual-table purge, already
         idempotent).
      3. Delete graph nodes for repo_id (relationships cascade).
      4. Delete the ingestion_requests rows *last* — they're the only
         durable trail a retry could use to rediscover what's left to
         clean up if step 2 or 3 fails partway, so they must not be
         removed until both have fully succeeded.
    """
    try:
        guard = reserve_repo_mutation(get_engine(), repo_id)
    except RepositoryBusy as exc:
        raise HTTPException(
            status_code=409, detail=str(exc), headers={"Retry-After": "5"},
        ) from exc

    try:
        if db_utils.has_active_ingestion_for_repo(repo_id):
            raise HTTPException(
                status_code=409,
                detail=(
                    "Repository has an active ingestion; wait for it to "
                    "complete/fail (or recover it) before deleting."
                ),
                headers={"Retry-After": "5"},
            )

        ingestion_ids = db_utils.list_ingestion_ids_for_repo(repo_id)
        if not ingestion_ids:
            logger.info(f"delete_repo: nothing found for repo_id={repo_id[:8]}")
            return RepoDeleteResponse(
                status="not_found",
                repo_id=repo_id,
                ingestion_ids=[],
                nodes_deleted=0,
                ingestion_requests_deleted=0,
            )

        settings = get_settings()
        vector_store = HttpVectorStore(base_url=settings.VECTOR_STORE_SERVICE_URL)

        try:
            for ingestion_id in ingestion_ids:
                vector_store.delete_by_ingestion_id(ingestion_id)
        except Exception as e:
            logger.error(f"delete_repo: vector cleanup failed for {repo_id[:8]}: {e}")
            raise HTTPException(
                status_code=502,
                detail=(
                    "Vector cleanup failed; nothing else was deleted yet. "
                    f"Safe to retry. Error: {e}"
                ),
            )

        try:
            with SessionLocal() as session:
                nodes_deleted = CodebaseGraphPersistence(
                    session=session
                ).delete_repo_nodes(repo_id)
        except Exception as e:
            logger.error(f"delete_repo: graph cleanup failed for {repo_id[:8]}: {e}")
            raise HTTPException(
                status_code=500,
                detail=(
                    "Graph cleanup failed after vectors were already deleted. "
                    f"Safe to retry (vector deletion is idempotent). Error: {e}"
                ),
            )

        ingestion_requests_deleted = db_utils.delete_ingestion_requests(ingestion_ids)

        logger.info(
            f"delete_repo: repo_id={repo_id[:8]} deleted "
            f"{len(ingestion_ids)} ingestion(s), {nodes_deleted} node(s), "
            f"{ingestion_requests_deleted} ingestion_requests row(s)"
        )

        return RepoDeleteResponse(
            status="deleted",
            repo_id=repo_id,
            ingestion_ids=ingestion_ids,
            nodes_deleted=nodes_deleted,
            ingestion_requests_deleted=ingestion_requests_deleted,
        )
    finally:
        guard.close()
