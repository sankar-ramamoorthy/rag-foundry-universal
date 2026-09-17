"""Persist repo_id on ingestion_requests independently of graph rows (WP-R3, issue #166)

Before this migration, document_nodes.repo_id was the *only* place the
repo_id <-> ingestion_id mapping existed. That means:

- A repository delete that fails after graph cleanup but before the
  ingestion_requests row is removed cannot be retried to completion once
  document_nodes rows are gone (list_ingestion_ids_for_repo has nothing
  left to enumerate).
- There is no way to resolve "the current completed generation" for a
  repo_id without joining through document_nodes, which is exactly the
  table that is empty/partial while a rebuild is in flight or after a
  failed attempt created no rows at all.

This migration adds a nullable repo_id column to ingestion_requests,
backfills it for existing repo-type rows from the (still intact)
document_nodes mapping, and indexes it. New rows are populated at HTTP
accept time (ingest_repo route) via build_repo_id(), which is a pure
deterministic function of git_url/local_path and needs no clone/DB
lookup to compute. Rows that cannot be backfilled (e.g. an attempt that
failed before any document_nodes were ever written) simply keep
repo_id NULL; there is nothing to recover for those historically, and no
code path depends on every historical row having one.

Revision ID: 20260917_repo_id_on_requests
Revises: 20260831_language_col
Create Date: 2026-09-17
"""

from alembic import op

revision = "20260917_repo_id_on_requests"
down_revision = "20260831_language_col"
branch_labels = None
depends_on = None

REQUESTS = "ingestion_service.ingestion_requests"
NODES = "ingestion_service.document_nodes"


def upgrade() -> None:
    op.execute(f"ALTER TABLE {REQUESTS} ADD COLUMN IF NOT EXISTS repo_id TEXT")

    # Backfill: one distinct repo_id per historical ingestion_id, where the
    # mapping is still recoverable from document_nodes. A repo-type ingestion
    # writes exactly one repo_id per attempt, so this is safe to take
    # unconditionally where a match exists.
    op.execute(
        f"""
        UPDATE {REQUESTS} AS r
        SET repo_id = backfill.repo_id
        FROM (
            SELECT DISTINCT ingestion_id, repo_id FROM {NODES}
        ) AS backfill
        WHERE r.ingestion_id = backfill.ingestion_id
          AND r.repo_id IS NULL
        """
    )

    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_ingestion_requests_repo_id "
        f"ON {REQUESTS} (repo_id)"
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_ingestion_requests_repo_status "
        f"ON {REQUESTS} (repo_id, status)"
    )

    op.execute(f"ANALYZE {REQUESTS}")


def downgrade() -> None:
    op.execute(
        "DROP INDEX IF EXISTS ingestion_service.ix_ingestion_requests_repo_status"
    )
    op.execute(
        "DROP INDEX IF EXISTS ingestion_service.ix_ingestion_requests_repo_id"
    )
    op.execute(f"ALTER TABLE {REQUESTS} DROP COLUMN IF EXISTS repo_id")
