# src/ingestion_service/core/status_manager.py
from __future__ import annotations

from datetime import datetime, UTC
from typing import Any, Dict
from uuid import UUID

from sqlalchemy.orm import Session

from src.core.models import IngestionRequest


class StatusManager:
    def __init__(self, session: Session) -> None:
        self._session = session

    # ---------------------------------------------------------
    # Creation
    # ---------------------------------------------------------
    def create_request(
        self,
        *,
        ingestion_id: UUID,
        source_type: str,
        metadata: Dict[str, Any],
    ) -> None:
        request = IngestionRequest()
        request.ingestion_id = ingestion_id
        request.source_type = source_type
        request.ingestion_metadata = metadata
        request.status = "accepted"

        self._session.add(request)
        self._session.commit()

    # ---------------------------------------------------------
    # Transitions
    # ---------------------------------------------------------
    def mark_running(self, ingestion_id: UUID) -> None:
        request = self._get_request(ingestion_id)
        request.status = "running"
        # Use timezone-aware UTC timestamps (Python 3.12+ compliant)
        request.started_at = datetime.now(UTC)
        self._session.commit()

    def mark_completed(self, ingestion_id: UUID) -> None:
        request = self._get_request(ingestion_id)
        request.status = "completed"
        request.finished_at = datetime.now(UTC)
        self._session.commit()

    def mark_failed(self, ingestion_id: UUID, *, error: str | None = None) -> None:
        request = self._get_request(ingestion_id)
        request.status = "failed"
        request.finished_at = datetime.now(UTC)

        if error:
            meta = request.ingestion_metadata or {}
            meta["error"] = error
            request.ingestion_metadata = meta

        self._session.commit()

    # ---------------------------------------------------------
    # Internal
    # ---------------------------------------------------------
    def _get_request(self, ingestion_id: UUID) -> IngestionRequest:
        request = (
            self._session.query(IngestionRequest)
            .filter_by(ingestion_id=ingestion_id)
            .first()
        )

        if request is None:
            raise RuntimeError(f"Ingestion request {ingestion_id} not found")

        return request
