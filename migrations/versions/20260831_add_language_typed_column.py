"""Promote language to a typed column on vector_chunks (WP-L6a, issue #85)

WP-S4B (DOCS/audit/04-Scalability-Plan.md) already named `language` as a
fourth column to promote alongside repo_id/doc_type "in a follow-up
migration" — only repo_id/doc_type (20260719_typed_filter_columns) and
later source_type (20260829_add_source_type_typed_column) were actually
done. WP-L2 (#83) shipped a second language extractor (TypeScript/
JavaScript), making a real language-scoped retrieval filter worth having:
`/v1/rag` can now scope a mixed-language repo's seed search to one
language (specs/003-language-aware-retrieval).

This migration:

- adds a language TEXT column,
- backfills it from source_metadata (a no-op for every existing row,
  since no row written before WP-L6a ever had a "language" key — this
  migration only makes new rows' language filterable, it does not
  retroactively classify old rows),
- indexes it (repo_id+language composite for hybrid_retrieve's exact
  filter shape, matching the (repo_id, doc_type) / (repo_id, source_type)
  indexes the two prior typed-column migrations added).

The column is a denormalized copy of a source_metadata key; the write
path (PgVectorStore.add) populates it from the same value, so it cannot
drift for new rows.

Revision ID: 20260831_language_col
Revises: 20260829_src_type
Create Date: 2026-08-31
"""

from alembic import op

revision = "20260831_language_col"
down_revision = "20260829_src_type"
branch_labels = None
depends_on = None

TABLE = "ingestion_service.vector_chunks"


def upgrade() -> None:
    op.execute(f"ALTER TABLE {TABLE} ADD COLUMN IF NOT EXISTS language TEXT")

    op.execute(
        f"UPDATE {TABLE} SET "
        "language = source_metadata->>'language' "
        "WHERE language IS NULL"
    )

    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_vector_chunks_repo_language "
        f"ON {TABLE} (repo_id, language)"
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_vector_chunks_language_col "
        f"ON {TABLE} (language)"
    )

    op.execute(f"ANALYZE {TABLE}")


def downgrade() -> None:
    op.execute(
        "DROP INDEX IF EXISTS ingestion_service.ix_vector_chunks_repo_language"
    )
    op.execute(
        "DROP INDEX IF EXISTS ingestion_service.ix_vector_chunks_language_col"
    )
    op.execute(f"ALTER TABLE {TABLE} DROP COLUMN IF EXISTS language")
