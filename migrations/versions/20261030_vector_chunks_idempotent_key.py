"""Unique key on vector_chunks so batch writes are idempotent (issue #287)

A vector batch whose client call timed out may already be committed; the
client now retries, and the insert uses ON CONFLICT DO NOTHING on this key.
The migration deletes no data: if duplicates already exist it aborts with
a message so the owner can decide, instead of silently dropping rows.

Plain CREATE UNIQUE INDEX (not CONCURRENTLY): migrations/env.py runs all
migrations inside one transaction. On a large table this builds under a
write lock; run it with ingestion idle.

Revision ID: 20261030_vc_idempotent_key
Revises: 20260919_node_provenance
Create Date: 2026-10-30
"""

from alembic import op

revision = "20261030_vc_idempotent_key"
down_revision = "20260919_node_provenance"
branch_labels = None
depends_on = None

TABLE = "ingestion_service.vector_chunks"
INDEX = "uq_vector_chunks_ingestion_chunk_index"


def upgrade() -> None:
    op.execute(f"""
        DO $$
        DECLARE dup bigint;
        BEGIN
            SELECT count(*) INTO dup FROM (
                SELECT 1 FROM {TABLE}
                GROUP BY ingestion_id, chunk_id, chunk_index
                HAVING count(*) > 1
            ) d;
            IF dup > 0 THEN
                RAISE EXCEPTION
                    '% duplicate key groups in vector_chunks (#287)', dup;
            END IF;
        END $$;
    """)
    op.execute(
        f"CREATE UNIQUE INDEX IF NOT EXISTS {INDEX} "
        f"ON {TABLE} (ingestion_id, chunk_id, chunk_index)"
    )


def downgrade() -> None:
    op.execute(f"DROP INDEX IF EXISTS ingestion_service.{INDEX}")
