"""#161 entrypoint-independent admission and worker lifetime management."""

from collections.abc import Callable
import logging
import threading
from uuid import UUID

from sqlalchemy.orm import Session

from src.core.database_session import get_engine
from src.core.ingestion_ownership import (
    AdvisoryGuard, owned_metadata, reconcile_ingestions, reserve_ingestion,
)
from src.core.models import IngestionRequest
from src.core.status_manager import StatusManager
from src.core.worker_context import ownership_check


logger = logging.getLogger(__name__)


def _fail_if_active(ingestion_id: UUID, error: str) -> None:
    try:
        with Session(get_engine()) as session:
            if session.get(IngestionRequest, ingestion_id) is not None:
                StatusManager(session).mark_failed(ingestion_id, error=error)
    except Exception:
        # Retain the active row for reconciliation after DB availability returns.
        logger.exception("Could not record ingestion failure for %s", ingestion_id)


def _run_owned(
    guard: AdvisoryGuard, ingestion_id: UUID, target: Callable, kwargs: dict,
) -> None:
    token = ownership_check.set(guard.check)
    error = "Ingestion worker returned without recording a terminal status"
    try:
        guard.check()
        target(ingestion_id=ingestion_id, **kwargs)
    except BaseException as exc:
        error = f"Ingestion worker interrupted: {exc}"
        logger.exception("Owned ingestion worker failed: %s", ingestion_id)
    finally:
        ownership_check.reset(token)
        try:
            _fail_if_active(ingestion_id, error)
        finally:
            guard.close()


def submit_ingestion(
    *, ingestion_id: UUID, source_type: str, metadata: dict,
    target: Callable, prepare: Callable[[], dict], repo_id: str | None = None,
) -> None:
    """No upload read, accepted row or thread is created before reservation.

    A single owner connection transfers from request to worker only at start().
    The request must never use/close it after a successful thread launch.

    repo_id (repository ingestion only, #166) also reserves the repo-scope
    lock so a concurrent delete of the same repository cannot interleave.
    """
    engine = get_engine()
    reconcile_ingestions(engine)
    guard = reserve_ingestion(engine, ingestion_id, repo_id=repo_id)
    try:
        kwargs = prepare()
        guard.check()
        with Session(engine) as session:
            StatusManager(session).create_request(
                ingestion_id=ingestion_id, source_type=source_type,
                metadata=owned_metadata(metadata), repo_id=repo_id,
            )
        threading.Thread(
            target=_run_owned, args=(guard, ingestion_id, target, kwargs),
            daemon=True, name=f"ingestion-{ingestion_id}",
        ).start()
    except BaseException as exc:
        try:
            _fail_if_active(ingestion_id, f"Ingestion acceptance failed: {exc}")
        finally:
            guard.close()
        raise


def recovery_loop(stop: threading.Event, *, interval: float = 5.0) -> None:
    """Recover dead owners even when another API process remains alive."""
    while not stop.wait(interval):
        try:
            reconcile_ingestions(get_engine())
        except Exception:
            logger.exception("Ingestion recovery sweep failed; will retry")
