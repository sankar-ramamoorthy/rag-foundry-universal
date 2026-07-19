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
from sqlalchemy import text
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.orm import Session
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
            pre_count = self._session.query(DocumentNode).filter_by(repo_id=repo_id).count()
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
            logger.info(f"[MS12] Repo {repo_id}: deleted {deleted_count} old document nodes")
            return deleted_count
        except SQLAlchemyError as e:
            logger.error(f"[MS12] Error deleting nodes for repo {repo_id}: {e}")
            self._session.rollback()
            raise


    BULK_BATCH_SIZE = 1000

    def persist_graph(
        self,
        repo_id: str,
        nodes: List[dict],
        relationships: List[dict],
    ) -> dict:
        """
        Atomically replace a repo's graph (F-06/F-09, WP-S3).

        Delete + node insert + relationship insert run in ONE transaction:
        any failure rolls back everything, leaving the previous graph
        intact. A transaction-scoped Postgres advisory lock keyed on
        repo_id serializes concurrent rebuilds of the same repo, so two
        ingests can never interleave delete/insert (F-11 mitigation).

        Relationship endpoints resolve through the in-memory
        canonical_id -> document_id map of the nodes being inserted — no
        per-edge queries. Edges referencing unknown endpoints are skipped
        (same behavior as before); duplicate edges are absorbed by
        ON CONFLICT DO NOTHING on uq_document_relationship.

        Node dict fields are the same as the old upsert_nodes contract:
        relative_path, optional symbol_path/canonical_id, title, doc_type,
        source, summary, text, ingestion_id.

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
        canonical_to_doc: dict = {}
        for node in nodes:
            relative_path = node.get("relative_path", "Unknown")
            canonical_id = node.get("canonical_id") or build_canonical_id(
                relative_path, node.get("symbol_path")
            )
            document_id = str(uuid.uuid4())
            canonical_to_doc[canonical_id] = document_id
            node_rows.append(
                {
                    "document_id": document_id,
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
                }
            )

        rel_rows: List[dict] = []
        skipped_relationships = 0
        for rel in relationships:
            from_doc = canonical_to_doc.get(rel["from_canonical_id"])
            to_doc = canonical_to_doc.get(rel["to_canonical_id"])
            if not from_doc or not to_doc:
                logger.warning(
                    f"Skipping relationship: {rel['from_canonical_id']} -> "
                    f"{rel['to_canonical_id']} (nodes missing)"
                )
                skipped_relationships += 1
                continue
            rel_rows.append(
                {
                    "from_document_id": from_doc,
                    "to_document_id": to_doc,
                    "relation_type": rel["relation_type"],
                    "relationship_metadata": rel.get("relationship_metadata", {}),
                }
            )

        batch = self.BULK_BATCH_SIZE
        try:
            with self._session.begin():
                # Blocks a concurrent rebuild of the same repo until this
                # transaction commits or rolls back.
                self._session.execute(
                    text("SELECT pg_advisory_xact_lock(hashtextextended(:key, 0))"),
                    {"key": f"repo_graph:{repo_id}"},
                )
                deleted = (
                    self._session.query(DocumentNode)
                    .filter(DocumentNode.repo_id == repo_id)
                    .delete(synchronize_session=False)
                )
                for start in range(0, len(node_rows), batch):
                    self._session.bulk_insert_mappings(
                        DocumentNode, node_rows[start:start + batch]
                    )
                for start in range(0, len(rel_rows), batch):
                    stmt = (
                        pg_insert(DocumentRelationship.__table__)
                        .values(rel_rows[start:start + batch])
                        .on_conflict_do_nothing(constraint="uq_document_relationship")
                    )
                    self._session.execute(stmt)
        except SQLAlchemyError:
            logger.exception(
                f"Atomic graph persist failed for repo {repo_id}; "
                f"previous graph left intact"
            )
            raise

        logger.info(
            f"Repo {repo_id}: replaced {deleted} old nodes with "
            f"{len(node_rows)} nodes / {len(rel_rows)} relationships "
            f"({skipped_relationships} edges skipped)"
        )
        return {
            "deleted": deleted,
            "nodes": len(node_rows),
            "relationships": len(rel_rows),
            "skipped_relationships": skipped_relationships,
        }
    # -----------------------------
    # Retrieval
    # -----------------------------
    def get_node_by_canonical_id(self, repo_id: str, canonical_id: str) -> Optional[DocumentNode]:
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

    def close(self):
        """Close the session if created internally."""
        if not self._external_session:
            self._session.close()
