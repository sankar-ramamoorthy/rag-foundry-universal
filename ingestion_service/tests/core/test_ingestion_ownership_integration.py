"""#161 real PostgreSQL ownership, death and conservative legacy recovery."""

import os
import subprocess
import sys
from uuid import uuid4

import pytest
from sqlalchemy import create_engine, delete
from sqlalchemy.orm import Session

from src.core.ingestion_ownership import (
    AdmissionBusy, owned_metadata, reconcile_ingestions, reserve_ingestion,
)
from src.core.models import IngestionRequest
from src.core.status_manager import StatusManager


pytestmark = pytest.mark.integration


@pytest.fixture
def ownership_db():
    engine = create_engine(os.environ["DATABASE_URL"])
    assert engine.url.database.endswith("_test"), "Only an isolated test database"
    attempts = []
    yield engine, attempts
    with engine.begin() as connection:
        connection.execute(delete(IngestionRequest).where(
            IngestionRequest.ingestion_id.in_(attempts),
        ))
    engine.dispose()


def create_attempt(engine, attempt, *, managed=True):
    with Session(engine) as session:
        StatusManager(session).create_request(
            ingestion_id=attempt, source_type="repo",
            metadata=owned_metadata({}) if managed else {},
        )


def test_live_owner_survives_reconcile_and_blocks_other_process(ownership_db):
    engine, attempts = ownership_db
    attempt = uuid4()
    attempts.append(attempt)
    with reserve_ingestion(engine, attempt):
        create_attempt(engine, attempt)
        assert reconcile_ingestions(engine) == 0
        with pytest.raises(AdmissionBusy):
            reserve_ingestion(engine, uuid4())
        with Session(engine) as session:
            assert session.get(IngestionRequest, attempt).status == "accepted"
    assert reconcile_ingestions(engine) == 1
    with Session(engine) as session:
        request = session.get(IngestionRequest, attempt)
        assert request.status == "failed"
        assert request.finished_at is not None
        assert "partial data retained" in request.ingestion_metadata["error"]
    assert reconcile_ingestions(engine) == 0
    with reserve_ingestion(engine, uuid4()):
        pass


def test_legacy_rows_need_explicit_stopped_worker_confirmation(ownership_db):
    engine, attempts = ownership_db
    attempt = uuid4()
    attempts.append(attempt)
    create_attempt(engine, attempt, managed=False)
    assert reconcile_ingestions(engine) == 0
    with pytest.raises(AdmissionBusy):
        reserve_ingestion(engine, uuid4())
    assert reconcile_ingestions(engine, include_legacy=True) == 1


def test_terminal_recovery_cannot_be_overwritten_by_stale_worker(ownership_db):
    engine, attempts = ownership_db
    attempt = uuid4()
    attempts.append(attempt)
    create_attempt(engine, attempt)
    with Session(engine) as stale:
        held = stale.get(IngestionRequest, attempt)
        assert held.status == "accepted"
        stale.commit()
        assert reconcile_ingestions(engine) == 1
        for action in (
            lambda: StatusManager(stale).mark_running(attempt),
            lambda: StatusManager(stale).mark_completed(attempt),
            lambda: StatusManager(stale).update_embed_progress(attempt, {}),
        ):
            with pytest.raises(RuntimeError, match="already terminal"):
                action()
            stale.rollback()
        StatusManager(stale).mark_failed(attempt, error="late exception")
    with Session(engine) as fresh:
        request = fresh.get(IngestionRequest, attempt)
        assert request.status == "failed"
        assert "database ownership is absent" in request.ingestion_metadata["error"]


@pytest.mark.parametrize("running", [False, True])
def test_hard_process_death_releases_owner_and_retains_progress(ownership_db, running):
    engine, attempts = ownership_db
    attempt = uuid4()
    attempts.append(attempt)
    # A separate interpreter owns the lock; kill bypasses all Python finally blocks.
    program = """
import os, sys, time
from uuid import UUID
from sqlalchemy import create_engine
from sqlalchemy.orm import Session
from src.core.ingestion_ownership import reserve_ingestion, owned_metadata
from src.core.status_manager import StatusManager
engine = create_engine(os.environ['DATABASE_URL'])
attempt = UUID(sys.argv[1])
guard = reserve_ingestion(engine, attempt)
with Session(engine) as session:
    status = StatusManager(session)
    status.create_request(
        ingestion_id=attempt, source_type='repo', metadata=owned_metadata({}),
    )
    if sys.argv[2] == 'True':
        status.mark_running(attempt)
        status.update_embed_progress(
            attempt, {'stage': 'embedding', 'chunks_persisted': 14},
        )
print('ready', flush=True)
time.sleep(60)
"""
    child = subprocess.Popen(
        [sys.executable, "-c", program, str(attempt), str(running)],
        stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True,
    )
    try:
        # Readiness uses a bounded wait even when the child fails before printing.
        import queue
        import threading
        ready = queue.Queue()
        threading.Thread(
            target=lambda: ready.put(child.stdout.readline()), daemon=True,
        ).start()
        assert ready.get(timeout=15).strip() == "ready"
        assert reconcile_ingestions(engine) == 0
        child.kill()
        child.communicate(timeout=10)
        assert reconcile_ingestions(engine) == 1
        with Session(engine) as session:
            request = session.get(IngestionRequest, attempt)
            assert request.status == "failed"
            assert request.finished_at is not None
            if running:
                assert request.ingestion_metadata["embed_progress"] == {
                    "stage": "failed", "chunks_persisted": 14,
                }
    finally:
        if child.poll() is None:
            child.kill()
        child.communicate(timeout=10)
