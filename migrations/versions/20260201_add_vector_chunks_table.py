"""Add VectorChunks table linked to DocumentNodes

Revision ID: 20260201_chunks
Revises: 20260131_docnodes
Create Date: 2026-02-01
"""

from alembic import op

revision = "20260201_chunks"
down_revision = "20260131_docnodes"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Ensure pgvector extension exists
    op.execute("CREATE EXTENSION IF NOT EXISTS vector")

    # Create vector_chunks table with ON DELETE CASCADE
    op.execute("""
    CREATE TABLE IF NOT EXISTS ingestion_service.vector_chunks (
        id SERIAL PRIMARY KEY,
        vector vector(768) NOT NULL,
        ingestion_id UUID NOT NULL,
        chunk_id TEXT NOT NULL,
        chunk_index INT NOT NULL,
        chunk_strategy TEXT NOT NULL,
        chunk_text TEXT NOT NULL,
        source_metadata JSONB NOT NULL DEFAULT '{}'::jsonb,
        provider TEXT NOT NULL DEFAULT 'ollama',
        document_id UUID
            REFERENCES ingestion_service.document_nodes(document_id)
            ON DELETE CASCADE
    )
    """)


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS ingestion_service.vector_chunks")
