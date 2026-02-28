"""Add vectors table using pgvector (with chunk text + metadata + provider)

Revision ID: 20251229_vectors
Revises: bb0f22648df9
Create Date: 2025-12-29
"""

from typing import Sequence, Union
from alembic import op

revision: str = "20251229_vectors"  # 16 chars ✓ (was "20251229_add_vectors_table")
down_revision: Union[str, Sequence[str], None] = "bb0f22648df9"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Enable pgvector extension
    op.execute("CREATE EXTENSION IF NOT EXISTS vector")

    # Create vectors table with provider column
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS ingestion_service.vectors (
            id SERIAL PRIMARY KEY,
            vector vector(768) NOT NULL,
            ingestion_id UUID NOT NULL,
            chunk_id TEXT NOT NULL,
            chunk_index INT NOT NULL,
            chunk_strategy TEXT NOT NULL,
            chunk_text TEXT NOT NULL,
            source_metadata JSONB NOT NULL DEFAULT '{}',
            provider TEXT NOT NULL DEFAULT 'ollama'
        )
        """
    )


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS ingestion_service.vectors")
