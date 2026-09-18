# src/ingestion_service/core/status_manager.py
from __future__ import annotations

from datetime import datetime, UTC
from typing import Any, Dict
from uuid import UUID

from sqlalchemy.orm import Session

from src.core.models import IngestionRequest
from src.core.worker_context import check_ownership


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
        repo_id: str | None = None,
    ) -> None:
        request = IngestionRequest()
        request.ingestion_id = ingestion_id
        request.source_type = source_type
        request.ingestion_metadata = metadata
        request.status = "accepted"
        request.repo_id = repo_id

        self._session.add(request)
        self._session.commit()

    # ---------------------------------------------------------
    # Transitions
    # ---------------------------------------------------------
    def mark_running(self, ingestion_id: UUID) -> None:
        request = self._get_request(ingestion_id)
        self._require_active(request)
        request.status = "running"
        # Use timezone-aware UTC timestamps (Python 3.12+ compliant)
        request.started_at = datetime.now(UTC)
        self._session.commit()

    def mark_completed(self, ingestion_id: UUID) -> None:
        request = self._get_request(ingestion_id)
        self._require_active(request)
        request.status = "completed"
        request.finished_at = datetime.now(UTC)
        self._set_progress_stage(request, "completed")
        self._session.commit()

    def mark_failed(self, ingestion_id: UUID, *, error: str | None = None) -> None:
        request = self._get_request(ingestion_id)
        if request.status not in ("accepted", "running"):
            self._session.rollback()
            return  # Preserve the first terminal outcome and recovery reason.
        request.status = "failed"
        request.finished_at = datetime.now(UTC)
        self._set_progress_stage(request, "failed")

        if error:
            meta = dict(request.ingestion_metadata or {})
            meta["error"] = error
            request.ingestion_metadata = meta

        self._session.commit()

    def update_embed_progress(self, ingestion_id: UUID, progress: dict) -> None:
        request = self._get_request(ingestion_id)
        self._require_active(request)
        request.ingestion_metadata = {
            **(request.ingestion_metadata or {}), "embed_progress": dict(progress),
        }
        self._session.commit()

    def record_generation_start(
        self,
        ingestion_id: UUID,
        *,
        parent_generation_id: str | None = None,
        chunking_config_version: str | None = None,
        embedding_config_version: str | None = None,
    ) -> None:
        """Issue #196 (T020/T025/R4/R6): record this generation's lineage
        identity as soon as it's known, before graph build begins.

        parent_generation_id is set whenever a prior generation existed for
        this repo_id (resolve_current_generation), regardless of
        force_full_rebuild -- it records lineage, not "was reused from"
        (data-model.md). chunking/embedding_config_version are this run's
        active config identity, compared against the prior generation's
        recorded values by the FR-006 reuse gate.
        """
        request = self._get_request(ingestion_id)
        self._require_active(request)
        if parent_generation_id is not None:
            request.parent_generation_id = parent_generation_id
        request.chunking_config_version = chunking_config_version
        request.embedding_config_version = embedding_config_version
        self._session.commit()

    def record_completion_lineage(
        self,
        ingestion_id: UUID,
        *,
        is_incremental: bool,
        commit_sha: str | None = None,
    ) -> None:
        """Issue #196 (T026/T030/T031): record lineage fields only known
        once the run has (almost) completed -- whether FR-004's reuse
        classification actually ran, and the resolved source commit SHA
        for a git-backed ingestion (None for local_path, R5).
        """
        request = self._get_request(ingestion_id)
        self._require_active(request)
        request.is_incremental = is_incremental
        if commit_sha is not None:
            request.commit_sha = commit_sha
        self._session.commit()

    @staticmethod
    def _set_progress_stage(request: IngestionRequest, stage: str) -> None:
        meta = request.ingestion_metadata or {}
        if "embed_progress" in meta:
            request.ingestion_metadata = {
                **meta, "embed_progress": {**meta["embed_progress"], "stage": stage},
            }

    # ---------------------------------------------------------
    # Internal
    # ---------------------------------------------------------
    @staticmethod
    def _require_active(request: IngestionRequest) -> None:
        if request.status not in ("accepted", "running"):
            raise RuntimeError(
                "Ingestion already terminal; refusing stale worker update",
            )

    def _get_request(self, ingestion_id: UUID) -> IngestionRequest:
        check_ownership()
        request = (
            self._session.query(IngestionRequest)
            .filter_by(ingestion_id=ingestion_id)
            .populate_existing()
            .with_for_update()
            .first()
        )

        if request is None:
            raise RuntimeError(f"Ingestion request {ingestion_id} not found")

        return request
