"""
MS4 Persistence Layer: CodebaseGraphPersistence

Handles saving and retrieving code repository graphs to/from Postgres.
Supports deterministic upserts using repo_id + canonical_id, and manages
document nodes, relationships, and vector links.

Requires:
- SQLAlchemy ORM models: DocumentNode, DocumentRelationship #, VectorChunk
- RepoGraphBuilder output nodes and relationships
"""

from typing import List, Optional, Tuple
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


    def upsert_nodes(self, repo_id: str, nodes: List[dict]) -> None:
        """
        Upsert a list of nodes (functions, classes, modules) into document_nodes.

        Each node dict must include:
        - relative_path: path relative to repo root
        - symbol_path: optional symbol path (for functions/methods)
        - title: display title
        - doc_type: function/class/module
        - source: source file path
        - summary: optional summary
        """

        # ----------------------
        # MS12 Repo-Level Deletion
        # ----------------------
        try:
            with self._session.begin():  # atomic transaction
                deleted_count = (
                    self._session.query(DocumentNode)
                    .filter(DocumentNode.repo_id == repo_id)
                    .delete(synchronize_session=False)
                )
                logger.info(f"[MS12] Repo {repo_id}: deleted {deleted_count} old document nodes")
        except SQLAlchemyError as e:
            logger.error(f"Failed to delete old nodes for repo {repo_id}: {e}")
            self._session.rollback()
            raise

        # ----------------------
        # Insert New Nodes
        # ----------------------
        for node in nodes:
            try:
                if "title" not in node:
                    node["title"] = "Untitled"
                if "doc_type" not in node:
                    node["doc_type"] = "unknown"
                if "source" not in node:
                    node["source"] = node.get("relative_path", "unknown_source")
                if "relative_path" not in node:
                    node["relative_path"] = "Unknown"
                if "canonical_id" not in node:
                    node["canonical_id"] = build_canonical_id(node["relative_path"], node.get("symbol_path"))
                canonical_id = node["canonical_id"]
                logger.debug(f"upsert_nodes canonical_id = {canonical_id}")
                document_node_data = {
                    'repo_id': repo_id,
                    'canonical_id': canonical_id,
                    'relative_path': node.get('relative_path', 'unknown'),
                    'symbol_path': node.get('symbol_path'),
                    'title': node.get('title', 'Untitled'),
                    'summary': node.get('summary', ''),
                    'source': node.get('source', node.get('relative_path', 'unknown')),
                    'ingestion_id': str(node.get('ingestion_id')),
                    'doc_type': node.get('doc_type', 'unknown'),
                    'text': node.get('text', ''),
                }
                new_node = DocumentNode(**document_node_data)
                self._session.add(new_node)
                logger.debug(f"[MS12] Inserted DocumentNode with canonical_id : {canonical_id}")

            except SQLAlchemyError as e:
                logger.error(f"Error upserting node {node.get('canonical_id', 'unknown')}: {e}")
                self._session.rollback()
                raise

        # Commit all inserts
        try:
            self._session.commit()
        except SQLAlchemyError as e:
            logger.error(f"Error committing new nodes for repo {repo_id}: {e}")
            self._session.rollback()
            raise

    # -----------------------------
    # Document Relationships
    # -----------------------------
    def upsert_relationships(self, repo_id: str, relationships: List[dict]) -> None:
        """
        Upsert relationships between nodes into document_relationships.

        Expected relationship format:

        {
            "from_canonical_id": str,
            "to_canonical_id": str,
            "relation_type": str,
            "relationship_metadata": dict
        }
        """

        for rel in relationships:
            from_canonical = rel["from_canonical_id"]
            to_canonical = rel["to_canonical_id"]

            try:
                from_node = (
                    self._session.query(DocumentNode)
                    .filter_by(repo_id=repo_id, canonical_id=from_canonical)
                    .first()
                )
                to_node = (
                    self._session.query(DocumentNode)
                    .filter_by(repo_id=repo_id, canonical_id=to_canonical)
                    .first()
                )

                if not from_node or not to_node:
                    logger.warning(
                        f"Skipping relationship: {from_canonical} -> {to_canonical} (nodes missing)"
                    )
                    continue

                existing = (
                    self._session.query(DocumentRelationship)
                    .filter_by(
                        from_document_id=from_node.document_id,
                        to_document_id=to_node.document_id,
                        relation_type=rel["relation_type"]
                    )
                    .first()
                )

                if existing:
                    existing.relationship_metadata = rel.get(
                        "relationship_metadata",
                        existing.relationship_metadata
                    )
                    logger.debug(
                        f"Updated DocumentRelationship: {from_canonical} -> {to_canonical}"
                    )
                else:
                    new_rel = DocumentRelationship(
                        from_document_id=from_node.document_id,
                        to_document_id=to_node.document_id,
                        relation_type=rel["relation_type"],
                        relationship_metadata=rel.get("relationship_metadata", {})
                    )
                    self._session.add(new_rel)
                    logger.debug(
                        f"Inserted DocumentRelationship: {from_canonical} -> {to_canonical}"
                    )

            except SQLAlchemyError as e:
                logger.error(
                    f"Error upserting relationship {from_canonical} -> {to_canonical}: {e}"
                )
                self._session.rollback()
                raise

        self._session.commit()
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

    def close(self):
        """Close the session if created internally."""
        if not self._external_session:
            self._session.close()
