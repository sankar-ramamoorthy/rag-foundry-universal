"""Create ingestion_requests table with timestamps

Revision ID: bb0f22648df9
Revises:
Create Date: 2025-12-20 14:49:36.004278
"""

from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID

# revision identifiers, used by Alembic.
revision: str = "bb0f22648df9"
down_revision: Union[str, Sequence[str], None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table(
        "ingestion_requests",
        sa.Column("ingestion_id", UUID(as_uuid=True), primary_key=True, nullable=False),
        sa.Column("source_type", sa.String(), nullable=False),
        sa.Column("ingestion_metadata", sa.JSON(), nullable=True),
        sa.Column(
            "status", sa.String(), server_default=sa.text("'pending'"), nullable=False
        ),
        sa.Column(
            "created_at",
            sa.TIMESTAMP(),
            server_default=sa.text("NOW()"),
            nullable=False,
        ),
        sa.Column("started_at", sa.TIMESTAMP(), nullable=True),
        sa.Column("finished_at", sa.TIMESTAMP(), nullable=True),
        schema="ingestion_service",
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_table("ingestion_requests", schema="ingestion_service")
