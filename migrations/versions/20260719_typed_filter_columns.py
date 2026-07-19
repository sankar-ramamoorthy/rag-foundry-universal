"""Promote repo_id/doc_type to typed columns on vector_chunks (WP-S4B)

Issue #30 made repo_id filtering correctness-critical on every query;
keeping it in JSONB is both a scan cost and — because pgvector's HNSW
post-filters — a recall risk as the table grows. This migration:

- adds repo_id TEXT and doc_type TEXT columns,
- backfills them from source_metadata (historical rows included),
- indexes them (btree; composite repo_id+doc_type for the hybrid
  query's exact shape),
- drops the two JSONB expression indexes they replace.

The columns are denormalized copies of source_metadata keys; the write
path populates both from the same values, so they cannot drift for new
rows.

Revision ID: 20260719_typed_cols
Revises: 20260718_vc_idx
Create Date: 2026-07-19
"""

from alembic import op

revision = "20260719_typed_cols"
down_revision = "20260718_vc_idx"
branch_labels = None
depends_on = None

TABLE = "ingestion_service.vector_chunks"


def upgrade() -> None:
    op.execute(f"ALTER TABLE {TABLE} ADD COLUMN IF NOT EXISTS repo_id TEXT")
    op.execute(f"ALTER TABLE {TABLE} ADD COLUMN IF NOT EXISTS doc_type TEXT")

    op.execute(
        f"UPDATE {TABLE} SET "
        "repo_id = source_metadata->>'repo_id', "
        "doc_type = source_metadata->>'doc_type' "
        "WHERE repo_id IS NULL AND doc_type IS NULL"
    )

    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_vector_chunks_repo_doc "
        f"ON {TABLE} (repo_id, doc_type)"
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_vector_chunks_doc_type_col "
        f"ON {TABLE} (doc_type)"
    )

    # superseded JSONB expression indexes (20260718_vc_idx)
    op.execute("DROP INDEX IF EXISTS ingestion_service.ix_vector_chunks_doc_type")
    op.execute("DROP INDEX IF EXISTS ingestion_service.ix_vector_chunks_repo_id")

    op.execute(f"ANALYZE {TABLE}")


def downgrade() -> None:
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_vector_chunks_doc_type "
        f"ON {TABLE} ((source_metadata->>'doc_type'))"
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_vector_chunks_repo_id "
        f"ON {TABLE} ((source_metadata->>'repo_id'))"
    )
    op.execute("DROP INDEX IF EXISTS ingestion_service.ix_vector_chunks_repo_doc")
    op.execute(
        "DROP INDEX IF EXISTS ingestion_service.ix_vector_chunks_doc_type_col"
    )
    op.execute(f"ALTER TABLE {TABLE} DROP COLUMN IF EXISTS repo_id")
    op.execute(f"ALTER TABLE {TABLE} DROP COLUMN IF EXISTS doc_type")
