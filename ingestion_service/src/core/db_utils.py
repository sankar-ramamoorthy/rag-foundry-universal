# ingestion_service/src/core/db_utils.py
"""
Database utilities for ingestion_service.

This module centralizes all database access logic so that:
- API routes remain thin (HTTP only)
- DB logic is reusable and testable
- No duplicate SQL queries exist in endpoints
"""

from typing import Optional, List, Dict
from uuid import UUID
import logging

from sqlalchemy import func

from .database_session import get_sessionmaker
from .models import IngestionRequest
from shared.models.document_node import DocumentNode
from shared.models.document_relationship import DocumentRelationship

logger = logging.getLogger(__name__)
SessionLocal = get_sessionmaker()


# ==============================================================
# INGESTION HELPERS
# ==============================================================

def create_ingestion_request(
    source_type: str,
    metadata: Dict,
    ingestion_id: Optional[UUID] = None,
) -> UUID:
    """
    Create a new ingestion request row.
    """
    from uuid import uuid4

    if not ingestion_id:
        ingestion_id = uuid4()

    with SessionLocal() as session:
        req = IngestionRequest()
        req.ingestion_id = ingestion_id
        req.source_type = source_type
        req.ingestion_metadata = metadata
        req.status = "accepted"

        session.add(req)
        session.commit()

        logger.info(f"Created ingestion request {ingestion_id}")

    return ingestion_id


def get_ingestion_status(ingestion_id: UUID) -> Optional[str]:
    """
    Get ingestion status by ID.
    """
    with SessionLocal() as session:
        req = (
            session.query(IngestionRequest)
            .filter_by(ingestion_id=ingestion_id)
            .first()
        )
        return req.status if req else None


# ==============================================================
# CHUNK HELPERS
# ==============================================================

def get_chunk_texts_by_ingestion_id(ingestion_id: str) -> List[str]:
    """
    Return all chunk texts for a given ingestion_id.
    Used by llm_service summarization — no vector math involved.

    ADR compliance: ingestion_db is owned exclusively by ingestion_service.
    llm_service calls GET /v1/chunks/{ingestion_id} which calls this function.
    No other service queries ingestion_db directly.
    """
    from shared.models.vector_chunk import VectorChunk

    with SessionLocal() as session:
        rows = (
            session.query(VectorChunk.chunk_text)
            .filter(VectorChunk.ingestion_id == ingestion_id)
            .all()
        )
        texts = [row.chunk_text for row in rows]
        logger.info(
            f"DB: get_chunk_texts_by_ingestion_id "
            f"ingestion_id={ingestion_id} → {len(texts)} chunks"
        )
        return texts


# ==============================================================
# REPOSITORY HELPERS
# ==============================================================

def list_complete_repos() -> List[Dict]:
    """
    Return metadata for all repositories with completed ingestions.

    Each dict contains:
        repo_id
        ingestion_id
        status
        created_at
        file_count
        node_count
        ingestion_metadata
    """
    with SessionLocal() as session:

        repo_rows = (
            session.query(
                DocumentNode.repo_id,
                DocumentNode.ingestion_id,
                IngestionRequest.status,
                IngestionRequest.created_at,
            )
            .join(
                IngestionRequest,
                DocumentNode.ingestion_id == IngestionRequest.ingestion_id,
            )
            .filter(IngestionRequest.status == "completed")
            .group_by(
                DocumentNode.repo_id,
                DocumentNode.ingestion_id,
                IngestionRequest.status,
                IngestionRequest.created_at,
            )
            .all()
        )

        results: List[Dict] = []

        # JSON columns can't be grouped in Postgres, so fetch the
        # ingestion metadata (git_url/local_path/…) in a second query
        # keyed by the already-grouped ingestion_ids (issue #30 Part 5).
        ingestion_ids = [row[1] for row in repo_rows]
        metadata_by_ingestion = dict(
            session.query(
                IngestionRequest.ingestion_id,
                IngestionRequest.ingestion_metadata,
            )
            .filter(IngestionRequest.ingestion_id.in_(ingestion_ids))
            .all()
        ) if ingestion_ids else {}

        for repo_id, ingestion_id, status, created_at in repo_rows:

            node_count = (
                session.query(func.count(DocumentNode.document_id))
                .filter(DocumentNode.repo_id == repo_id)
                .scalar()
            )

            file_count = (
                session.query(func.count(func.distinct(DocumentNode.relative_path)))
                .filter(DocumentNode.repo_id == repo_id)
                .scalar()
            )

            results.append(
                {
                    "repo_id": repo_id,
                    "ingestion_id": ingestion_id,
                    "status": status,
                    "created_at": created_at,
                    "file_count": int(file_count or 0),
                    "node_count": int(node_count or 0),
                    "ingestion_metadata": metadata_by_ingestion.get(ingestion_id),
                }
            )

        logger.info(f"DB: Found {len(results)} complete repositories")

        return results


def list_ingestion_ids_for_repo(repo_id: str) -> List[str]:
    """
    Return every historical ingestion_id ever associated with repo_id.

    #166: repo_id is now persisted directly on ingestion_requests (set at
    HTTP accept time), so this is the primary source and — unlike the old
    document_nodes-only lookup — still works after graph rows are gone
    (retry after a delete that failed partway through, an attempt that
    never wrote a single node). document_nodes.repo_id is kept as a
    fallback union for historical rows predating the repo_id column that
    the migration's backfill could not reach (should not happen post-
    backfill, but costs nothing to keep as a second source of truth).
    This intentionally does not filter by IngestionRequest.status: a repo
    delete must sweep every ingestion_id ever recorded for it, active or not.
    """
    with SessionLocal() as session:
        from_requests = (
            session.query(IngestionRequest.ingestion_id)
            .filter(IngestionRequest.repo_id == repo_id)
            .distinct()
            .all()
        )
        from_nodes = (
            session.query(DocumentNode.ingestion_id)
            .filter(DocumentNode.repo_id == repo_id)
            .distinct()
            .all()
        )
        ingestion_ids = sorted({
            str(row[0]) for row in (*from_requests, *from_nodes)
        })
        logger.info(
            f"DB: {len(ingestion_ids)} historical ingestion_id(s) found for "
            f"repo {repo_id[:8]}"
        )
        return ingestion_ids


def superseded_ingestion_ids_for_repo(
    repo_id: str, current_ingestion_id: str,
) -> List[str]:
    """Every historical ingestion_id for repo_id other than current_ingestion_id.

    #166: a successful rebuild's persist_graph atomically replaces
    document_nodes for repo_id (DocumentNode enforces one row per
    (repo_id, canonical_id), so two generations' graph rows can never
    coexist) -- but vector_store_service has no such constraint and keeps
    every ingestion_id's vectors until something explicitly deletes them.
    Left alone, every rebuild leaks the previous generation's vectors:
    they still match repo_id-filtered search after their document_ids have
    been deleted from document_nodes, degrading retrieval with dead links
    forever. Used only after the new generation is confirmed complete.
    """
    current = str(current_ingestion_id)
    return [i for i in list_ingestion_ids_for_repo(repo_id) if i != current]


def has_active_ingestion_for_repo(repo_id: str) -> bool:
    """True if repo_id has an accepted/running ingestion_requests row (#166).

    Used to reject a delete while a repository is actively being built, so
    delete and ingest never mutate the same repository concurrently even
    outside the advisory-lock race window (e.g. a delete arriving between
    admission and the repo lock being taken is still visible here once the
    accepted row is committed).
    """
    with SessionLocal() as session:
        active = session.query(IngestionRequest.ingestion_id).filter(
            IngestionRequest.repo_id == repo_id,
            IngestionRequest.status.in_(("accepted", "running")),
        ).first()
        return active is not None


def delete_ingestion_requests(ingestion_ids: List[str]) -> int:
    """
    Delete ingestion_requests rows for the given ingestion_ids.

    Issue #158: this is the *last* step of a repo delete — ingestion_requests
    is the only durable record a retry could use to rediscover what still
    needs cleaning up if an earlier step (vector or graph deletion) failed
    partway, so it must not be removed until those steps have both
    succeeded for every id in the list. Idempotent: deleting an id that's
    already gone is a no-op, not an error.
    """
    if not ingestion_ids:
        return 0

    with SessionLocal() as session:
        deleted = (
            session.query(IngestionRequest)
            .filter(IngestionRequest.ingestion_id.in_(ingestion_ids))
            .delete(synchronize_session=False)
        )
        session.commit()
        logger.info(f"DB: deleted {deleted} ingestion_requests row(s)")
        return deleted


# ==============================================================
# GRAPH HELPERS
# ==============================================================

def _document_node_owner(session, repo_id: str) -> Optional[str]:
    """The single ingestion_id currently reflected in document_nodes for
    repo_id, or None if it has no graph rows right now.

    persist_graph atomically deletes+replaces ALL of repo_id's document_nodes
    inside one transaction (a transaction-scoped advisory lock keyed on
    repo_id serializes concurrent rebuilds — see CodebaseGraphPersistence.
    persist_graph), and DocumentNode enforces a unique (repo_id, canonical_id)
    constraint. So at most one ingestion_id's rows can exist for repo_id at
    any moment; there is no schema-level way for two generations to coexist.
    """
    return session.query(DocumentNode.ingestion_id).filter(
        DocumentNode.repo_id == repo_id,
    ).distinct().scalar()


def resolve_current_generation(repo_id: str) -> Optional[str]:
    """Return the ingestion_id to serve graph reads from for repo_id (#166),
    or None if there is nothing safe to serve right now.

    Critically, persist_graph's atomic replace runs at *graph-build* time,
    well before embedding finishes and mark_completed is written — so
    "document_nodes currently holds ingestion_id X" does NOT by itself mean
    X's ingestion is complete (or even that X's vectors exist yet). Only
    return an ingestion_id whose ingestion_requests.status is "completed";
    a rebuild in flight (graph replaced, embedding still running, or the
    attempt later failed) must not be served as if it were a stable
    generation, even though its rows are the only ones physically present.
    """
    with SessionLocal() as session:
        owner = _document_node_owner(session, repo_id)
        if owner is None:
            return None
        status = session.query(IngestionRequest.status).filter(
            IngestionRequest.ingestion_id == owner,
        ).scalar()
        return str(owner) if status == "completed" else None


def generation_status(repo_id: str) -> str:
    """"ready" (document_nodes hold a completed generation), "building" (an
    ingestion is accepted/running for repo_id -- its document_nodes, if any,
    may be a not-yet-embedded rebuild and must not be treated as stable),
    "failed" (the most recent ingestion for repo_id failed and none is
    currently active), or "unknown" (no ingestion_requests row for repo_id
    at all, or the owner of its document_nodes has no matching row -- both
    should not happen post-migration but are handled rather than assumed).
    """
    with SessionLocal() as session:
        owner = _document_node_owner(session, repo_id)
        if owner is not None:
            status = session.query(IngestionRequest.status).filter(
                IngestionRequest.ingestion_id == owner,
            ).scalar()
            if status == "completed":
                return "ready"
            if status in ("accepted", "running"):
                return "building"
        latest_status = session.query(IngestionRequest.status).filter(
            IngestionRequest.repo_id == repo_id,
        ).order_by(IngestionRequest.created_at.desc()).limit(1).scalar()
        if latest_status in ("accepted", "running"):
            return "building"
        if latest_status == "failed":
            return "failed"
        return "unknown"


def get_document_nodes_by_canonical_ids(
    repo_id: str,
    canonical_ids: List[str],
) -> List[DocumentNode]:
    """
    Return DocumentNode rows for a repo's *current completed generation*
    and list of canonical_ids. Used by graph lookup endpoint.
    """
    if not canonical_ids:
        return []

    current_ingestion_id = resolve_current_generation(repo_id)
    if current_ingestion_id is None:
        return []

    with SessionLocal() as session:
        nodes = (
            session.query(DocumentNode)
            .filter(
                DocumentNode.repo_id == repo_id,
                DocumentNode.ingestion_id == current_ingestion_id,
                DocumentNode.canonical_id.in_(canonical_ids),
            )
            .all()
        )

        logger.info(
            f"DB: {len(nodes)} nodes found for "
            f"{len(canonical_ids)} canonical_ids "
            f"in repo {repo_id[:8]} generation {str(current_ingestion_id)[:8]}"
        )

        return nodes


def get_full_graph_for_repo(repo_id: str) -> Dict:
    """
    Load nodes and relationships for a repo's *current completed generation*
    only (#166) — never a mix of an old generation and an in-flight rebuild's
    partial rows, and never two completed generations at once.
    """
    current_ingestion_id = resolve_current_generation(repo_id)
    if current_ingestion_id is None:
        return {
            "nodes": {}, "relationships": {},
            "generation_status": generation_status(repo_id),
        }

    with SessionLocal() as session:

        nodes = (
            session.query(DocumentNode)
            .filter(
                DocumentNode.repo_id == repo_id,
                DocumentNode.ingestion_id == current_ingestion_id,
            )
            .all()
        )

        if not nodes:
            return {
                "nodes": {}, "relationships": {}, "generation_status": "ready",
            }

        node_data = {node.canonical_id: node for node in nodes}
        document_ids = {node.document_id for node in nodes}

        relationships = (
            session.query(DocumentRelationship)
            .filter(DocumentRelationship.from_document_id.in_(document_ids))
            .all()
        )

        doc_id_to_canonical = {node.document_id: node.canonical_id for node in nodes}

        rel_data: Dict = {}
        for rel in relationships:
            from_cid = doc_id_to_canonical.get(rel.from_document_id)
            to_cid = doc_id_to_canonical.get(rel.to_document_id)
            if from_cid and to_cid:
                if from_cid not in rel_data:
                    rel_data[from_cid] = []
                rel_data[from_cid].append({
                    "to_canonical_id": to_cid,
                    "relation_type": rel.relation_type,
                })

        logger.info(
            f"DB: get_full_graph_for_repo repo={repo_id[:8]} "
            f"— {len(node_data)} nodes, {len(rel_data)} relationship groups"
        )

        return {
            "nodes": node_data,
            "relationships": rel_data,
            "generation_status": "ready",
        }
