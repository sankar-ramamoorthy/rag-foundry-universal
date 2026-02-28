# shared\models\document_node.py
"""
ORM model for DocumentNodes table using pgvector.

Supports:
- Structured RAG documents
- Codebase graph entities
- Deterministic canonical identity (ADR-031)

Global identity model:
    (repo_id, canonical_id)

This prevents cross-repository collisions.
"""

from typing import TYPE_CHECKING
from sqlalchemy import (
    Column,
    String,
    ForeignKey,
    Text,
    UniqueConstraint,
    Index,
)
from sqlalchemy.orm import relationship
from shared.models.base import Base
import uuid
import logging
from pgvector.sqlalchemy import Vector

if TYPE_CHECKING:
    from .vector_chunk import VectorChunk
    from .document_relationship import DocumentRelationship

logger = logging.getLogger(__name__)


class DocumentNode(Base):
    """
    Represents a logical document or code entity.

    Global identity (ADR-031):
        repo_id + canonical_id

    document_id remains internal DB primary key.
    """

    __tablename__ = "document_nodes"
    __table_args__ = (
        UniqueConstraint("repo_id", "canonical_id", name="uq_repo_canonical"),
        Index("ix_repo_canonical", "repo_id", "canonical_id"),
        {"schema": "ingestion_service"},
    )

    # ------------------------------------------------------------------
    # Primary Key
    # ------------------------------------------------------------------
    document_id: str = Column(
        String,
        primary_key=True,
        default=lambda: str(uuid.uuid4()),
    )

    # ------------------------------------------------------------------
    # ADR-031 Identity Fields (NEW)
    # ------------------------------------------------------------------
    repo_id: str = Column(
        String,
        nullable=False,
        index=True,
        doc="Repository UUID namespace",
    )

    canonical_id: str = Column(
        String,
        nullable=False,
        index=True,
        doc="Deterministic path[#symbol] identifier",
    )

    relative_path: str = Column(
        String,
        nullable=False,
        doc="Path relative to repository root",
    )

    symbol_path: str = Column(
        String,
        nullable=True,
        doc="Optional symbol path for classes/functions/methods",
    )

    # ------------------------------------------------------------------
    # RAG Fields
    # ------------------------------------------------------------------
    title: str = Column(String, nullable=False)
    summary: str = Column(Text, nullable=False)

    summary_embedding: list[float] = Column(
        Vector(768),
        nullable=True,
        doc="768-dim embedding vector (pgvector)",
    )

    source: str = Column(
        String,
        nullable=False,
        doc="Original source (repo, file, URI)",
    )

    ingestion_id: str = Column(
        String,
        ForeignKey("ingestion_service.ingestion_requests.ingestion_id"),
        nullable=False,
    )

    doc_type: str = Column(
        String,
        nullable=False,
        doc="Type/category (code, document, adr, etc.)",
    )


    text: str = Column(
        Text,  # This will store the full source code of the artifact.
        nullable=True,
        doc="Source code text of the artifact."
    )
    # ------------------------------------------------------------------
    # Relationships
    # ------------------------------------------------------------------
    vector_chunks: "list[VectorChunk]" = relationship(
        "VectorChunk",
        back_populates="document_node",
        cascade="all, delete-orphan",
    )

    outgoing_relationships: "list[DocumentRelationship]" = relationship(
        "DocumentRelationship",
        foreign_keys="[DocumentRelationship.from_document_id]",
        back_populates="from_node",
        cascade="all, delete-orphan",
    )

    incoming_relationships: "list[DocumentRelationship]" = relationship(
        "DocumentRelationship",
        foreign_keys="[DocumentRelationship.to_document_id]",
        back_populates="to_node",
        cascade="all, delete-orphan",
    )
