"""Add HNSW ANN index + filter indexes to vector_chunks (audit F-10, WP-S4)

- HNSW (cosine) on vector_chunks.vector so similarity search stops being
  a sequential scan over every row.
- btree expression indexes on source_metadata->>'doc_type' and
  source_metadata->>'repo_id' for the JSONB filters the query path uses
  today (real columns are a follow-up migration per WP-S4).
- btree on document_id for the /v1/vectors/search-by-doc expansion path.

Plain CREATE INDEX (not CONCURRENTLY): migrations/env.py runs all
migrations inside one transaction, where CONCURRENTLY is not allowed.
The write lock during index build is acceptable at current table sizes;
revisit alongside the WP-S4 follow-up if that changes.

Revision ID: 20260718_vc_idx
Revises: 20260301_vector_dim
Create Date: 2026-07-18
"""

from alembic import op

revision = "20260718_vc_idx"
down_revision = "20260301_vector_dim"
branch_labels = None
depends_on = None


INDEXES = [
    (
        "ix_vector_chunks_hnsw",
        "CREATE INDEX IF NOT EXISTS ix_vector_chunks_hnsw "
        "ON ingestion_service.vector_chunks "
        "USING hnsw (vector vector_cosine_ops)",
    ),
    (
        "ix_vector_chunks_doc_type",
        "CREATE INDEX IF NOT EXISTS ix_vector_chunks_doc_type "
        "ON ingestion_service.vector_chunks ((source_metadata->>'doc_type'))",
    ),
    (
        "ix_vector_chunks_repo_id",
        "CREATE INDEX IF NOT EXISTS ix_vector_chunks_repo_id "
        "ON ingestion_service.vector_chunks ((source_metadata->>'repo_id'))",
    ),
    (
        "ix_vector_chunks_document_id",
        "CREATE INDEX IF NOT EXISTS ix_vector_chunks_document_id "
        "ON ingestion_service.vector_chunks (document_id)",
    ),
]


def upgrade() -> None:
    for _, create_stmt in INDEXES:
        op.execute(create_stmt)
    op.execute("ANALYZE ingestion_service.vector_chunks")


def downgrade() -> None:
    for name, _ in INDEXES:
        op.execute(f"DROP INDEX IF EXISTS ingestion_service.{name}")
