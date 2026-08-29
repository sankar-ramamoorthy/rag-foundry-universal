"""Promote source_type to a typed column on vector_chunks (issue #64)

hybrid_retrieve() (ADR-045) filters code-repo seed search on
metadata_filter={"doc_type": "code", ...}, but ingestion never writes
doc_type="code" (codebase ingestion writes doc_type="python source"),
so the filter never matches and every query silently falls back to an
unfiltered repo-scoped search. The actual "is this code" marker every
chunk already carries is source_type ("code" vs "file", written in
pipeline.py::_chunk and already used correctly by simple_service.py's
{"source_type": {"ne": "code"}} filter) — it just wasn't promoted out
of the source_metadata JSONB the way WP-S4B promoted repo_id/doc_type.

This migration:

- adds a source_type TEXT column,
- backfills it from source_metadata (historical rows included),
- indexes it (btree; composite repo_id+source_type for hybrid_retrieve's
  exact filter shape, matching the (repo_id, doc_type) index WP-S4B
  added for the old shape).

The column is a denormalized copy of a source_metadata key; the write
path populates it from the same value, so it cannot drift for new rows.

Revision ID: 20260829_src_type
Revises: 20260719_typed_cols
Create Date: 2026-08-29
"""

from alembic import op

revision = "20260829_src_type"
down_revision = "20260719_typed_cols"
branch_labels = None
depends_on = None

TABLE = "ingestion_service.vector_chunks"


def upgrade() -> None:
    op.execute(f"ALTER TABLE {TABLE} ADD COLUMN IF NOT EXISTS source_type TEXT")

    op.execute(
        f"UPDATE {TABLE} SET "
        "source_type = source_metadata->>'source_type' "
        "WHERE source_type IS NULL"
    )

    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_vector_chunks_repo_source_type "
        f"ON {TABLE} (repo_id, source_type)"
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_vector_chunks_source_type_col "
        f"ON {TABLE} (source_type)"
    )

    op.execute(f"ANALYZE {TABLE}")


def downgrade() -> None:
    op.execute(
        "DROP INDEX IF EXISTS ingestion_service.ix_vector_chunks_repo_source_type"
    )
    op.execute(
        "DROP INDEX IF EXISTS ingestion_service.ix_vector_chunks_source_type_col"
    )
    op.execute(f"ALTER TABLE {TABLE} DROP COLUMN IF EXISTS source_type")
