# ingestion_service/src/core/models.py (classic style - Pyright perfect)
import uuid
from sqlalchemy import Column, String, JSON, TIMESTAMP, Boolean
from sqlalchemy.dialects.postgresql import UUID

from sqlalchemy.sql import text

from shared.models.base import Base


class IngestionRequest(Base):
    __tablename__ = "ingestion_requests"
    __table_args__ = {"schema": "ingestion_service"}
    ingestion_id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    source_type = Column(String, nullable=False)
    # WP-R3 (#166): repository identity independent of document_nodes, so a
    # repo delete/generation lookup works even when graph rows are absent
    # (retry after graph cleanup, or a rebuild attempt still in flight).
    repo_id = Column(String, nullable=True)
    ingestion_metadata = Column(JSON, nullable=True)
    status = Column(String, nullable=False, server_default=text("'pending'"))
    created_at = Column(TIMESTAMP, server_default=text("NOW()"), nullable=False)
    started_at = Column(TIMESTAMP, nullable=True)
    finished_at = Column(TIMESTAMP, nullable=True)
    # Incremental ingestion + snapshot lineage (issue #196).
    commit_sha = Column(String, nullable=True)
    parent_generation_id = Column(UUID(as_uuid=True), nullable=True)
    is_incremental = Column(Boolean, nullable=False, server_default=text("false"))
    chunking_config_version = Column(String, nullable=True)
    embedding_config_version = Column(String, nullable=True)
