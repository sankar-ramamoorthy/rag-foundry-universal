"""Update vector dimensions from 768 to 1024 for mxbai-embed-large
Revision ID: 20260301_vector_dim
Revises: 20260201_rels
Create Date: 2026-03-01
"""
from alembic import op

revision = "20260301_vector_dim"
down_revision = "20260201_rels"
branch_labels = None
depends_on = None

def upgrade() -> None:
    # Drop existing vector indexes before altering column types
    op.execute("DROP INDEX IF EXISTS ingestion_service.vectors_vector_idx")
    op.execute("DROP INDEX IF EXISTS ingestion_service.vector_chunks_vector_idx")
    op.execute("DROP INDEX IF EXISTS ingestion_service.document_nodes_summary_embedding_idx")

    # Alter vector columns to 1024 dimensions (mxbai-embed-large)
    op.execute("""
        ALTER TABLE ingestion_service.vectors
        ALTER COLUMN vector TYPE vector(1024)
    """)
    op.execute("""
        ALTER TABLE ingestion_service.vector_chunks
        ALTER COLUMN vector TYPE vector(1024)
    """)
    op.execute("""
        ALTER TABLE ingestion_service.document_nodes
        ALTER COLUMN summary_embedding TYPE vector(1024)
    """)

def downgrade() -> None:
    op.execute("""
        ALTER TABLE ingestion_service.vectors
        ALTER COLUMN vector TYPE vector(768)
    """)
    op.execute("""
        ALTER TABLE ingestion_service.vector_chunks
        ALTER COLUMN vector TYPE vector(768)
    """)
    op.execute("""
        ALTER TABLE ingestion_service.document_nodes
        ALTER COLUMN summary_embedding TYPE vector(768)
    """)
