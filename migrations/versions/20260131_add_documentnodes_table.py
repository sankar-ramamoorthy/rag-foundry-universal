"""Add DocumentNodes table using pgvector with canonical identity

Revision ID: 20260131_docnodes
Revises: 20251229_vectors
Create Date: 2026-01-31
"""

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = "20260131_docnodes"
down_revision = "20251229_vectors"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Ensure pgvector extension exists
    op.execute("CREATE EXTENSION IF NOT EXISTS vector")

    # Create DocumentNodes table
    op.execute("""
    CREATE TABLE IF NOT EXISTS ingestion_service.document_nodes (
        document_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
        repo_id UUID NOT NULL,
        canonical_id TEXT NOT NULL,
        relative_path TEXT NOT NULL,
        symbol_path TEXT,
        title TEXT NOT NULL,
        summary TEXT NOT NULL,
        summary_embedding vector(768),
        source TEXT NOT NULL,
        ingestion_id UUID NOT NULL REFERENCES ingestion_service.ingestion_requests(ingestion_id),
        doc_type TEXT NOT NULL,
        text TEXT        
    )
    """)

    # Add Unique constraint for ADR-031 identity (repo_id, canonical_id)
    op.execute("""
    ALTER TABLE ingestion_service.document_nodes
    ADD CONSTRAINT uq_repo_canonical UNIQUE (repo_id, canonical_id)
    """)

    # Create indexes for performance
    op.execute("CREATE INDEX ix_repo_canonical ON ingestion_service.document_nodes (repo_id, canonical_id)")

    # Optional: Index on ingestion_id if we plan to query by this frequently
    op.execute("CREATE INDEX ix_document_nodes_ingestion_id ON ingestion_service.document_nodes (ingestion_id)")

def downgrade() -> None:
    """Drop tables in reverse order to respect foreign key constraints."""
    # Drop dependent tables first
    op.execute("DROP TABLE IF EXISTS ingestion_service.document_relationships")
    op.execute("DROP TABLE IF EXISTS ingestion_service.vector_chunks")

    # Finally, drop the document_nodes table
    op.execute("DROP TABLE IF EXISTS ingestion_service.document_nodes")
