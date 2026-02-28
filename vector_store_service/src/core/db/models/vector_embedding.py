# src/ingestion_service/core/db/models/vector_embedding.py
"""
DEPRECATED / NOT USED IN MS2a.

This model is not wired into the current vector storage pipeline. Live embeddings
are stored in the `ingestion_service.vectors` table via PgVectorStore (raw psycopg).

This ORM model exists as a possible future direction for unified SQLAlchemy-based
vector storage, but is currently unused. Do not import or use this model for
active development.

Current path: core/vectorstore/pgvector_store.py → ingestion_service.vectors table
"""

import uuid
from typing import Any

from sqlalchemy import Column, DateTime, Integer, Text, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import declarative_base
from pgvector.sqlalchemy import Vector

Base = declarative_base()


class VectorEmbedding(Base):
    __tablename__ = "vector_embeddings"
    __table_args__ = {"schema": "ingestion_service"}

    # 👇 THIS is what fixes Pyright
    def __init__(self, **kwargs: Any) -> None:
        super().__init__(**kwargs)

    id = Column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
    )

    ingestion_id = Column(
        UUID(as_uuid=True),
        nullable=False,
        index=True,
    )

    chunk_id = Column(Text, nullable=False)
    chunk_index = Column(Integer, nullable=False)
    chunk_strategy = Column(Text, nullable=False)

    embedding = Column(Vector(1536), nullable=False)

    created_at = Column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )
