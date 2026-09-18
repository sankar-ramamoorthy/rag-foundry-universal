# shared\models\document_relationship.py
"""
ORM model for DocumentRelationship table.
Tracks relationships between DocumentNodes.
"""

from typing import TYPE_CHECKING
from datetime import datetime
from sqlalchemy import (
    Column,
    Integer,
    String,
    ForeignKey,
    JSON,
    DateTime,
    Index,
    func,
)
from sqlalchemy.orm import relationship
from shared.models.base import Base
import logging

if TYPE_CHECKING:
    from .document_node import DocumentNode

logger = logging.getLogger(__name__)


class DocumentRelationship(Base):
    """
    Represents a relationship between two DocumentNodes.

    Attributes:
        id: Primary key
        from_document_id: source DocumentNode
        to_document_id: target DocumentNode
        relation_type: type of relationship (e.g., "explains", "supports")
        relationship_metadata: optional JSON metadata
        created_at: timestamp of creation
        from_node: SQLAlchemy relationship to source DocumentNode
        to_node: SQLAlchemy relationship to target DocumentNode
    """

    __tablename__ = "document_relationships"
    __table_args__ = (
        Index("ix_document_relationships_repo_id", "repo_id"),
        {"schema": "ingestion_service"},
    )
    logger.debug(
        "DocumentRelationship Represents a relationship between two DocumentNodes."
    )

    # -----------------------------
    # Primary Key
    # -----------------------------
    id: int = Column(Integer, primary_key=True, autoincrement=True)

    # -----------------------------
    # Foreign Keys
    # -----------------------------
    from_document_id: str = Column(
        ForeignKey("ingestion_service.document_nodes.document_id", ondelete="CASCADE"),
        nullable=False,
    )
    to_document_id: str = Column(
        ForeignKey("ingestion_service.document_nodes.document_id", ondelete="CASCADE"),
        nullable=False,
    )

    # -----------------------------
    # Relationship Metadata
    # -----------------------------
    relation_type: str = Column(String, nullable=False)
    relationship_metadata: dict = Column(JSON, nullable=False, default=dict)

    # R2 (issue #196): denormalized from either endpoint's
    # document_nodes.repo_id — both endpoints always share the same
    # repo_id (ADR-031's repository-scoping rule), so this makes the
    # every-ingestion "delete this repo's relationships" replace an
    # indexed, single-column scan instead of a join through document_nodes.
    repo_id: str = Column(String, nullable=False)
    created_at: datetime = Column(DateTime(timezone=True), server_default=func.now())

    # -----------------------------
    # Bidirectional Relationships
    # -----------------------------
    from_node: "DocumentNode" = relationship(
        "DocumentNode",
        foreign_keys=lambda: [DocumentRelationship.from_document_id],
        back_populates="outgoing_relationships",
    )

    to_node: "DocumentNode" = relationship(
        "DocumentNode",
        foreign_keys=lambda: [DocumentRelationship.to_document_id],
        back_populates="incoming_relationships",
    )
