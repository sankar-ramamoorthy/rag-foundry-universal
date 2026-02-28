# shared\models\vector_chunk.py
"""
ORM model for VectorChunks table using pgvector.
Represents embedding chunks linked to a DocumentNode.
"""

from typing import TYPE_CHECKING
from sqlalchemy import Column, String, JSON, Integer, ForeignKey
from sqlalchemy.orm import relationship
from shared.models.base import Base
import uuid

from pgvector.sqlalchemy import Vector  # pgvector type for SQLAlchemy

if TYPE_CHECKING:
    from .document_node import DocumentNode


class VectorChunk(Base):
    """
    Represents an embedding chunk of a document.

    Attributes:
        id: Primary key of the chunk.
        vector: 768-dimensional embedding vector stored as pgvector.
        ingestion_id: The ingestion request that produced this chunk.
        chunk_id: Unique identifier for the chunk within the ingestion.
        chunk_index: Sequential index of the chunk.
        chunk_strategy: Strategy used to create the chunk (e.g., 'sentence', 'paragraph').
        chunk_text: The text content of the chunk.
        source_metadata: JSON metadata about the source.
        provider: The embedding provider or source system.
        document_id: Foreign key linking to the parent DocumentNode.
        document_node: SQLAlchemy relationship to DocumentNode.
    """
    __tablename__ = "vectors"
    __table_args__ = {"schema": "ingestion_service"}

    # -----------------------------
    # Primary Key
    # -----------------------------
    id: int = Column(Integer, primary_key=True, autoincrement=True)

    # -----------------------------
    # Embedding & Ingestion Metadata
    # -----------------------------
    vector: list[float] = Column(Vector(768), nullable=False)  # pgvector column
    ingestion_id: str = Column(String, nullable=False)
    chunk_id: str = Column(String, nullable=False)
    chunk_index: int = Column(Integer, nullable=False)
    chunk_strategy: str = Column(String, nullable=False)
    chunk_text: str = Column(String, nullable=False)
    source_metadata: dict = Column(JSON, nullable=False, default=dict)  # fixed mutable default
    provider: str = Column(String, nullable=False, default="ollama")

    # -----------------------------
    # Relationship to DocumentNode
    # -----------------------------
    document_id: str = Column(
        ForeignKey("ingestion_service.document_nodes.document_id", ondelete="CASCADE"),
        nullable=True,
    )
    document_node: "DocumentNode" = relationship(
        "DocumentNode",
        back_populates="vector_chunks",
    )
