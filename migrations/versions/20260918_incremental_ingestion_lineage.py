"""Additive schema for incremental ingestion + snapshot lineage (issue #196)

All new columns are nullable or defaulted; no data migration is required
(data-model.md's opening note — NULL/default values correctly fall back
to full-ingestion behavior, they never cause an incorrect reuse decision).

ingestion_requests gains commit_sha, parent_generation_id, is_incremental,
chunking_config_version, embedding_config_version.

document_nodes gains content_hash (file-level rows only).

document_relationships gains repo_id (denormalized from either endpoint's
document_nodes.repo_id, R2) plus an index, so the every-ingestion
"DELETE FROM document_relationships WHERE repo_id = :repo_id" replace is
an indexed operation.

Revision ID: 20260918_incremental_lineage
Revises: 20260917_repo_id_on_requests
Create Date: 2026-09-18
"""

from alembic import op

revision = "20260918_incremental_lineage"
down_revision = "20260917_repo_id_on_requests"
branch_labels = None
depends_on = None

REQUESTS = "ingestion_service.ingestion_requests"
NODES = "ingestion_service.document_nodes"
RELATIONSHIPS = "ingestion_service.document_relationships"


def upgrade() -> None:
    op.execute(
        f"ALTER TABLE {REQUESTS} ADD COLUMN IF NOT EXISTS commit_sha TEXT"
    )
    op.execute(
        f"ALTER TABLE {REQUESTS} ADD COLUMN IF NOT EXISTS "
        "parent_generation_id UUID"
    )
    op.execute(
        f"ALTER TABLE {REQUESTS} ADD COLUMN IF NOT EXISTS "
        "is_incremental BOOLEAN NOT NULL DEFAULT FALSE"
    )
    op.execute(
        f"ALTER TABLE {REQUESTS} ADD COLUMN IF NOT EXISTS "
        "chunking_config_version TEXT"
    )
    op.execute(
        f"ALTER TABLE {REQUESTS} ADD COLUMN IF NOT EXISTS "
        "embedding_config_version TEXT"
    )

    op.execute(
        f"ALTER TABLE {NODES} ADD COLUMN IF NOT EXISTS content_hash TEXT"
    )

    op.execute(
        f"ALTER TABLE {RELATIONSHIPS} ADD COLUMN IF NOT EXISTS repo_id TEXT"
    )
    # Backfill existing rows from their from_document_id's repo_id (R2:
    # both endpoints always share the same repo_id, ADR-031's
    # repository-scoping rule).
    op.execute(
        f"""
        UPDATE {RELATIONSHIPS} AS r
        SET repo_id = n.repo_id
        FROM {NODES} AS n
        WHERE r.from_document_id = n.document_id
          AND r.repo_id IS NULL
        """
    )
    # Any row that still could not be backfilled (orphaned endpoint) gets
    # an empty-string sentinel so the NOT NULL constraint can be applied;
    # no live code path depends on a historical orphan's repo_id.
    op.execute(
        f"UPDATE {RELATIONSHIPS} SET repo_id = '' WHERE repo_id IS NULL"
    )
    op.execute(
        f"ALTER TABLE {RELATIONSHIPS} ALTER COLUMN repo_id SET NOT NULL"
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_document_relationships_repo_id "
        f"ON {RELATIONSHIPS} (repo_id)"
    )

    op.execute(f"ANALYZE {REQUESTS}")
    op.execute(f"ANALYZE {NODES}")
    op.execute(f"ANALYZE {RELATIONSHIPS}")


def downgrade() -> None:
    op.execute(
        "DROP INDEX IF EXISTS ingestion_service.ix_document_relationships_repo_id"
    )
    op.execute(f"ALTER TABLE {RELATIONSHIPS} DROP COLUMN IF EXISTS repo_id")

    op.execute(f"ALTER TABLE {NODES} DROP COLUMN IF EXISTS content_hash")

    op.execute(f"ALTER TABLE {REQUESTS} DROP COLUMN IF EXISTS embedding_config_version")
    op.execute(f"ALTER TABLE {REQUESTS} DROP COLUMN IF EXISTS chunking_config_version")
    op.execute(f"ALTER TABLE {REQUESTS} DROP COLUMN IF EXISTS is_incremental")
    op.execute(f"ALTER TABLE {REQUESTS} DROP COLUMN IF EXISTS parent_generation_id")
    op.execute(f"ALTER TABLE {REQUESTS} DROP COLUMN IF EXISTS commit_sha")
