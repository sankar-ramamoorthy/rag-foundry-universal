"""Additive schema for the ORIENT structural inventory (issue #197)

ingestion_requests gains structural_summary: a generation-aggregate JSON
blob (language counts, indexed/non-indexed file counts, heuristic
test/docs directories, gaps/unknowns) computed once deterministically
during ingestion and read directly by GET /v1/repos/{repo_id}/orient.
NULL for any generation ingested before this migration -- the endpoint
treats that as "re-ingest to populate" (409), not an empty inventory.

No document_nodes/document_relationships schema change is needed:
FILE/MANIFEST/SERVICE inventory nodes reuse the existing doc_type free
string column.

Revision ID: 20260919_orient_inventory
Revises: 20260918_incremental_lineage
Create Date: 2026-09-19
"""

from alembic import op

revision = "20260919_orient_inventory"
down_revision = "20260918_incremental_lineage"
branch_labels = None
depends_on = None

REQUESTS = "ingestion_service.ingestion_requests"


def upgrade() -> None:
    op.execute(
        f"ALTER TABLE {REQUESTS} ADD COLUMN IF NOT EXISTS structural_summary JSON"
    )
    op.execute(f"ANALYZE {REQUESTS}")


def downgrade() -> None:
    op.execute(f"ALTER TABLE {REQUESTS} DROP COLUMN IF EXISTS structural_summary")
