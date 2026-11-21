"""Additive verified source line span on document nodes (issue #412)

document_nodes gains start_line and end_line: the one-based inclusive line
range (source read API line convention: LF only) that provably holds the
node's stored text, computed at ingestion by
ingestion_service/src/core/codebase/source_span.py. NULL means no range was
verified, for any reason, including rows ingested before this migration;
consumers must read NULL as "location unknown", never guess one.

Plain ADD COLUMN with no default: metadata-only on Postgres, no table rewrite.

Revision ID: 20261121_node_source_span
Revises: 20261030_vc_idempotent_key
Create Date: 2026-11-21
"""

from alembic import op

revision = "20261121_node_source_span"
down_revision = "20261030_vc_idempotent_key"
branch_labels = None
depends_on = None

NODES = "ingestion_service.document_nodes"


def upgrade() -> None:
    op.execute(f"ALTER TABLE {NODES} ADD COLUMN IF NOT EXISTS start_line INTEGER")
    op.execute(f"ALTER TABLE {NODES} ADD COLUMN IF NOT EXISTS end_line INTEGER")


def downgrade() -> None:
    op.execute(f"ALTER TABLE {NODES} DROP COLUMN IF EXISTS end_line")
    op.execute(f"ALTER TABLE {NODES} DROP COLUMN IF EXISTS start_line")
