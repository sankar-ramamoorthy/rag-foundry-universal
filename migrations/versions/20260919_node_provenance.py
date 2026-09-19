"""Additive schema for source authority/subject/provenance (issue #199)

document_nodes gains provenance: a per-node JSON envelope (role, subject,
derivation, validity, classification -- see ADR-053) computed
deterministically at ingestion time by
ingestion_service/src/core/codebase/provenance_classifier.py. Origin is
NOT duplicated here -- it's the existing repo_id/canonical_id/
relative_path/source/ingestion_id/doc_type/content_hash columns.

NULL for any row ingested (or not yet re-ingested) before this
migration; every consumer must read that as "every facet unknown," not
a default interpretation.

Revision ID: 20260919_node_provenance
Revises: 20260919_orient_inventory
Create Date: 2026-09-19
"""

from alembic import op

revision = "20260919_node_provenance"
down_revision = "20260919_orient_inventory"
branch_labels = None
depends_on = None

NODES = "ingestion_service.document_nodes"


def upgrade() -> None:
    op.execute(f"ALTER TABLE {NODES} ADD COLUMN IF NOT EXISTS provenance JSON")
    op.execute(f"ANALYZE {NODES}")


def downgrade() -> None:
    op.execute(f"ALTER TABLE {NODES} DROP COLUMN IF EXISTS provenance")
