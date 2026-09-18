"""
MS4 Persistence Layer: CodebaseGraphPersistence

Handles saving and retrieving code repository graphs to/from Postgres.
Supports deterministic upserts using repo_id + canonical_id, and manages
document nodes, relationships, and vector links.

Requires:
- SQLAlchemy ORM models: DocumentNode, DocumentRelationship #, VectorChunk
- RepoGraphBuilder output nodes and relationships
"""

import uuid
from typing import List, Optional
from sqlalchemy import text, func, select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.orm import Session
from src.core.worker_context import check_ownership
from sqlalchemy.exc import SQLAlchemyError
import logging

from shared.models.document_node import DocumentNode
from shared.models.document_relationship import DocumentRelationship
#from shared.models.vector_chunk import VectorChunk
from src.core.database_session import get_sessionmaker
from src.core.codebase.identity import build_canonical_id

logger = logging.getLogger(__name__)
SessionLocal = get_sessionmaker()


class CodebaseGraphPersistence:
    """
    Service for persisting repository graphs into Postgres.
    Ensures deterministic upserts for nodes and relationships.
    """

    def __init__(self, session: Optional[Session] = None):
        self._external_session = session
        self._session = session or SessionLocal()

    # -----------------------------
    # Document Nodes
    # -----------------------------
    def delete_repo_nodes(self, repo_id: str) -> int:
        """
        Safely delete all document nodes for a given repo_id.
        Cascade deletes related vector chunks and relationships.

        Returns the number of nodes deleted.
        """
        try:
            # Count before deletion
            pre_count = (
                self._session.query(DocumentNode).filter_by(repo_id=repo_id).count()
            )
            if pre_count == 0:
                logger.info(f"[MS12] Repo {repo_id}: no nodes to delete")
                return 0

            # Delete nodes (cascade should handle relationships/vector chunks)
            deleted_count = (
                self._session.query(DocumentNode)
                .filter_by(repo_id=repo_id)
                .delete(synchronize_session=False)
            )
            self._session.commit()
            logger.info(
                f"[MS12] Repo {repo_id}: deleted {deleted_count} old document nodes"
            )
            return deleted_count
        except SQLAlchemyError as e:
            logger.error(f"[MS12] Error deleting nodes for repo {repo_id}: {e}")
            self._session.rollback()
            raise


    BULK_BATCH_SIZE = 1000

    # Every DocumentNode column except document_id (never re-assigned, so
    # a reused row keeps its original primary key, R1) and repo_id/
    # canonical_id (the ON CONFLICT target itself).
    _UPSERT_UPDATE_COLUMNS = (
        "relative_path",
        "symbol_path",
        "title",
        "summary",
        "source",
        "ingestion_id",
        "doc_type",
        "text",
        "content_hash",
    )

    def persist_graph(
        self,
        repo_id: str,
        nodes: List[dict],
        relationships: List[dict],
    ) -> dict:
        """
        Atomically upsert a repo's graph (F-06/F-09, WP-S3; R1/R2, issue #196).

        Node persistence is an upsert-by-(repo_id, canonical_id): a
        canonical_id whose row survives across generations keeps its
        original document_id (R1) — this is what lets vectors/relationships
        tied to that row survive a re-ingestion instead of being
        cascade-deleted. Every row present in the new node set, reused or
        not, is re-tagged to the new generation's ingestion_id.
        canonical_ids absent from the new node set are explicitly deleted
        (still cascades to their relationships/vectors, same as before).

        Relationship persistence is a full repo-scoped replace (R2): all
        of the repo's existing relationships are deleted and the freshly
        resolved set is inserted, regardless of node reuse — a reused-
        but-unchanged node's stale edges must not survive just because
        the node itself wasn't deleted.

        Delete + upsert + relationship replace run in ONE transaction: any
        failure rolls back everything, leaving the previous graph intact.
        A transaction-scoped Postgres advisory lock keyed on repo_id
        serializes concurrent rebuilds of the same repo, so two ingests
        can never interleave (F-11 mitigation).

        Relationship endpoints resolve through the in-memory
        canonical_id -> document_id map of the nodes being persisted — no
        per-edge queries. Edges referencing unknown endpoints are skipped
        (same behavior as before).

        Node dict fields are the same as the old upsert_nodes contract:
        relative_path, optional symbol_path/canonical_id, title, doc_type,
        source, summary, text, ingestion_id, optional content_hash.

        Relationship dict format:
        {
            "from_canonical_id": str,
            "to_canonical_id": str,
            "relation_type": str,
            "relationship_metadata": dict
        }

        Returns {"deleted", "nodes", "relationships", "skipped_relationships"}.
        """
        node_rows: List[dict] = []
        canonical_ids: List[str] = []
        for node in nodes:
            relative_path = node.get("relative_path", "Unknown")
            canonical_id = node.get("canonical_id") or build_canonical_id(
                relative_path, node.get("symbol_path")
            )
            canonical_ids.append(canonical_id)
            node_rows.append(
                {
                    # Only used for a brand-new row; ON CONFLICT DO UPDATE
                    # never overwrites an existing row's document_id (R1).
                    "document_id": str(uuid.uuid4()),
                    "repo_id": repo_id,
                    "canonical_id": canonical_id,
                    "relative_path": relative_path,
                    "symbol_path": node.get("symbol_path"),
                    "title": node.get("title", "Untitled"),
                    "summary": node.get("summary", ""),
                    "source": node.get("source", relative_path),
                    "ingestion_id": str(node.get("ingestion_id")),
                    "doc_type": node.get("doc_type", "unknown"),
                    "text": node.get("text", ""),
                    "content_hash": node.get("content_hash"),
                }
            )

        # Endpoints resolve to document_ids after the upsert commits (a
        # reused canonical_id's document_id isn't known until then, R1).
        rel_rows: List[dict] = [
            {
                "from_canonical_id": rel["from_canonical_id"],
                "to_canonical_id": rel["to_canonical_id"],
                "relation_type": rel["relation_type"],
                "relationship_metadata": rel.get("relationship_metadata", {}),
            }
            for rel in relationships
        ]

        batch = self.BULK_BATCH_SIZE
        check_ownership()
        try:
            with self._session.begin():
                # Blocks a concurrent rebuild of the same repo until this
                # transaction commits or rolls back.
                self._session.execute(
                    text("SELECT pg_advisory_xact_lock(hashtextextended(:key, 0))"),
                    {"key": f"repo_graph:{repo_id}"},
                )

                # 1) Upsert nodes: ON CONFLICT(repo_id, canonical_id) keeps
                #    document_id for a surviving row (R1).
                update_set = {
                    col: getattr(pg_insert(DocumentNode.__table__).excluded, col)
                    for col in self._UPSERT_UPDATE_COLUMNS
                }
                for start in range(0, len(node_rows), batch):
                    stmt = (
                        pg_insert(DocumentNode.__table__)
                        .values(node_rows[start:start + batch])
                        .on_conflict_do_update(
                            constraint="uq_repo_canonical",
                            set_=update_set,
                        )
                    )
                    self._session.execute(stmt)

                # 2) Delete canonical_ids genuinely absent from the new set
                #    (FR-008) — still cascades to relationships/vectors.
                deleted = (
                    self._session.query(DocumentNode)
                    .filter(DocumentNode.repo_id == repo_id)
                    .filter(~DocumentNode.canonical_id.in_(canonical_ids))
                    .delete(synchronize_session=False)
                    if canonical_ids
                    else self._session.query(DocumentNode)
                    .filter(DocumentNode.repo_id == repo_id)
                    .delete(synchronize_session=False)
                )

                # 3) Resolve the definitive canonical_id -> document_id map
                #    post-upsert (reused rows kept their original id).
                rows = self._session.execute(
                    select(DocumentNode.canonical_id, DocumentNode.document_id)
                    .where(DocumentNode.repo_id == repo_id)
                ).all()
                canonical_to_doc = {r.canonical_id: r.document_id for r in rows}

                # 4) Full repo-scoped relationship replace (R2) — a reused
                #    node's stale edges must not survive just because the
                #    node itself wasn't deleted.
                self._session.query(DocumentRelationship).filter(
                    DocumentRelationship.repo_id == repo_id
                ).delete(synchronize_session=False)

                resolved_rel_rows: List[dict] = []
                skipped_relationships = 0
                for rel in rel_rows:
                    from_doc = canonical_to_doc.get(rel["from_canonical_id"])
                    to_doc = canonical_to_doc.get(rel["to_canonical_id"])
                    if not from_doc or not to_doc:
                        logger.warning(
                            f"Skipping relationship: {rel['from_canonical_id']} -> "
                            f"{rel['to_canonical_id']} (nodes missing)"
                        )
                        skipped_relationships += 1
                        continue
                    resolved_rel_rows.append(
                        {
                            "repo_id": repo_id,
                            "from_document_id": from_doc,
                            "to_document_id": to_doc,
                            "relation_type": rel["relation_type"],
                            "relationship_metadata": rel["relationship_metadata"],
                        }
                    )

                for start in range(0, len(resolved_rel_rows), batch):
                    stmt = (
                        pg_insert(DocumentRelationship.__table__)
                        .values(resolved_rel_rows[start:start + batch])
                        .on_conflict_do_nothing(constraint="uq_document_relationship")
                    )
                    self._session.execute(stmt)
                check_ownership()  # Fail/roll back before publishing after lock loss.
        except SQLAlchemyError:
            logger.exception(
                f"Atomic graph persist failed for repo {repo_id}; "
                f"previous graph left intact"
            )
            raise

        logger.info(
            f"Repo {repo_id}: upserted {len(node_rows)} nodes "
            f"(deleted {deleted} removed), {len(resolved_rel_rows)} relationships "
            f"({skipped_relationships} edges skipped)"
        )
        return {
            "deleted": deleted,
            "nodes": len(node_rows),
            "relationships": len(resolved_rel_rows),
            "skipped_relationships": skipped_relationships,
        }
    # -----------------------------
    # Retrieval
    # -----------------------------
    def get_node_by_canonical_id(
        self, repo_id: str, canonical_id: str
    ) -> Optional[DocumentNode]:
        """
        Retrieve a document node by repo_id + canonical_id.
        """
        return (
            self._session.query(DocumentNode)
            .filter_by(repo_id=repo_id, canonical_id=canonical_id)
            .first()
        )

    def get_canonical_id_map(self, repo_id: str) -> dict:
        """
        Return {canonical_id: document_id (str)} for every node in the repo,
        in a single query (F-08: replaces per-node get_node_by_canonical_id).
        """
        rows = (
            self._session.query(DocumentNode.canonical_id, DocumentNode.document_id)
            .filter(DocumentNode.repo_id == repo_id)
            .all()
        )
        return {canonical_id: str(document_id) for canonical_id, document_id in rows}

    def iter_artifact_pages(
        self, repo_id: str, ingestion_id: str, *, page_size: int,
        max_artifact_bytes: int, expected_nodes: int,
    ):
        """Narrow keyset pages; never retain ORM nodes or a transaction over HTTP.

        Preflight checks bytes in PostgreSQL before selecting any text. Every
        page also guards the byte ceiling to fail closed if content changes.
        Full-operation mutation exclusion is a separate release prerequisite
        (#161/#166); these checks detect disappearance, not provide a lock.
        """
        if any(type(n) is not int or n <= 0 for n in (page_size, max_artifact_bytes)):
            raise ValueError("Page and artifact limits must be positive integers")
        if type(expected_nodes) is not int or expected_nodes < 0:
            raise ValueError("Expected node count must be a nonnegative integer")
        bind = self._session.get_bind()

        def assert_generation(session):
            total, owned = session.execute(select(
                func.count(DocumentNode.document_id),
                func.count(DocumentNode.document_id).filter(
                    DocumentNode.ingestion_id == ingestion_id
                ),
            ).where(DocumentNode.repo_id == repo_id)).one()
            if total != expected_nodes or owned != expected_nodes:
                raise RuntimeError("Repository generation changed during embedding")

        with Session(bind=bind) as session:
            assert_generation(session)
            oversize = session.execute(select(
                DocumentNode.canonical_id, func.octet_length(DocumentNode.text),
            ).where(
                DocumentNode.repo_id == repo_id,
                DocumentNode.ingestion_id == ingestion_id,
                func.octet_length(DocumentNode.text) > max_artifact_bytes,
            )).first()
            if oversize:
                raise ValueError(
                    f"Artifact {oversize[0]} is {oversize[1]} UTF-8 bytes; "
                    f"limit is {max_artifact_bytes}"
                )

        after = None
        seen = 0
        while True:
            with Session(bind=bind) as session:
                query = select(
                    DocumentNode.document_id, DocumentNode.canonical_id,
                    DocumentNode.relative_path, DocumentNode.doc_type,
                    DocumentNode.text,
                ).where(
                    DocumentNode.repo_id == repo_id,
                    DocumentNode.ingestion_id == ingestion_id,
                    func.coalesce(func.octet_length(DocumentNode.text), 0)
                    <= max_artifact_bytes,
                )
                if after is not None:
                    query = query.where(DocumentNode.document_id > after)
                rows = session.execute(
                    query.order_by(DocumentNode.document_id).limit(page_size)
                ).all()
            if not rows:
                break
            after = rows[-1].document_id
            seen += len(rows)
            # Named column rows contain no ORM relationship collections.
            yield rows
            del rows  # Release this page before allocating its successor.
        with Session(bind=bind) as session:
            assert_generation(session)
        if seen != expected_nodes:
            raise RuntimeError(
                "Repository artifacts disappeared or exceeded byte limit"
            )

    def close(self):
        """Close the session if created internally."""
        if not self._external_session:
            self._session.close()
