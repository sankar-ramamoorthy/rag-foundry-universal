"""Add DocumentRelationship table with unique constraint

Revision ID: 20260201_rels
Revises: 20260201_chunks
Create Date: 2026-02-01
"""

from alembic import op

revision = "20260201_rels"
down_revision = "20260201_chunks"
branch_labels = None
depends_on = None


def upgrade() -> None:
    """Create document_relationships table with FKs to document_nodes"""
    op.execute("""
    CREATE TABLE IF NOT EXISTS ingestion_service.document_relationships (
        id SERIAL PRIMARY KEY,
        from_document_id UUID NOT NULL REFERENCES ingestion_service.document_nodes(document_id) ON DELETE CASCADE,
        to_document_id UUID NOT NULL REFERENCES ingestion_service.document_nodes(document_id) ON DELETE CASCADE,
        relation_type TEXT NOT NULL,
        relationship_metadata JSONB NOT NULL DEFAULT '{}'::jsonb,
        created_at TIMESTAMPTZ DEFAULT now(),
        CONSTRAINT uq_document_relationship UNIQUE (from_document_id, to_document_id, relation_type)
    )
    """)


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS ingestion_service.document_relationships")
