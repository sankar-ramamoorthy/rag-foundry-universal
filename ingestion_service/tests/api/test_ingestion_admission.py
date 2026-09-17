"""#161 route admission and worker lifecycle regression tests."""

from types import SimpleNamespace
from unittest.mock import MagicMock
from uuid import uuid4

from fastapi import FastAPI
from fastapi.testclient import TestClient
import pytest

from src.api.v1 import ingest, codebase_ingest
from src.core import ingestion_jobs as jobs
from src.core.ingestion_ownership import AdmissionBusy, OwnershipLost
from src.core.worker_context import check_ownership, ownership_check


pytestmark = pytest.mark.unit


def test_file_saturation_does_not_read_upload(monkeypatch):
    upload = SimpleNamespace(
        file=MagicMock(), filename="a.txt", content_type="text/plain",
    )
    monkeypatch.setattr(
        ingest, "submit_ingestion", MagicMock(side_effect=AdmissionBusy("busy")),
    )
    with pytest.raises(ingest.HTTPException) as error:
        ingest.ingest_file(upload, None)
    assert error.value.status_code == 503
    assert error.value.headers == {"Retry-After": "5"}
    upload.file.read.assert_not_called()


@pytest.mark.parametrize("kind", ["file", "repo"])
def test_saturation_is_retryable_over_http(monkeypatch, kind):
    module = ingest if kind == "file" else codebase_ingest
    monkeypatch.setattr(
        module, "submit_ingestion", MagicMock(side_effect=AdmissionBusy("busy")),
    )
    app = FastAPI()
    app.include_router(module.router)
    with TestClient(app) as client:
        response = (
            client.post("/ingest/file", files={"file": ("a.txt", b"hello")})
            if kind == "file"
            else client.post("/ingest-repo", data={"git_url": "https://example/a.git"})
        )
    assert response.status_code == 503
    assert response.headers["Retry-After"] == "5"


@pytest.fixture
def job_mocks(monkeypatch):
    guard = MagicMock()
    monkeypatch.setattr(jobs, "get_engine", MagicMock())
    monkeypatch.setattr(jobs, "reconcile_ingestions", MagicMock())
    monkeypatch.setattr(jobs, "reserve_ingestion", MagicMock(return_value=guard))
    monkeypatch.setattr(jobs, "Session", MagicMock())
    manager = MagicMock()
    monkeypatch.setattr(jobs, "StatusManager", MagicMock(return_value=manager))
    thread = MagicMock()
    monkeypatch.setattr(jobs.threading, "Thread", thread)
    failed = MagicMock()
    monkeypatch.setattr(jobs, "_fail_if_active", failed)
    return guard, manager, thread, failed


@pytest.mark.parametrize("point", ["prepare", "create", "launch"])
def test_acceptance_failure_releases_owner(job_mocks, point):
    guard, manager, thread, failed = job_mocks
    prepare = MagicMock(return_value={})
    operation = {
        "prepare": prepare, "create": manager.create_request,
        "launch": thread.return_value.start,
    }[point]
    operation.side_effect = RuntimeError(point)
    attempt = uuid4()
    with pytest.raises(RuntimeError, match=point):
        jobs.submit_ingestion(
            ingestion_id=attempt, source_type="file", metadata={},
            target=MagicMock(), prepare=prepare,
        )
    guard.close.assert_called_once()
    failed.assert_called_once()
    if point != "launch":
        thread.return_value.start.assert_not_called()


def test_successful_launch_transfers_owner_to_worker(job_mocks):
    guard, manager, thread, failed = job_mocks
    jobs.submit_ingestion(
        ingestion_id=uuid4(), source_type="repo", metadata={},
        target=MagicMock(), prepare=lambda: {},
    )
    manager.create_request.assert_called_once()
    thread.return_value.start.assert_called_once()
    guard.close.assert_not_called()
    failed.assert_not_called()


def test_worker_lost_ownership_never_starts_target_and_releases(job_mocks):
    guard, _, _, failed = job_mocks
    guard.check.side_effect = OwnershipLost("lost")
    target = MagicMock()
    jobs._run_owned(guard, uuid4(), target, {})
    target.assert_not_called()
    guard.close.assert_called_once()
    failed.assert_called_once()
    assert ownership_check.get() is None


def test_work_boundary_checks_do_not_leak_between_threads():
    check = MagicMock(side_effect=OwnershipLost("lost"))
    token = ownership_check.set(check)
    try:
        with pytest.raises(OwnershipLost):
            check_ownership()
    finally:
        ownership_check.reset(token)
    check_ownership()


def test_lost_owner_cannot_commit_file_node():
    from src.core.crud.crud_document_node import create_document_node

    session = MagicMock()
    token = ownership_check.set(MagicMock(side_effect=OwnershipLost("lost")))
    try:
        with pytest.raises(OwnershipLost):
            create_document_node(
                session, document_id=uuid4(), title="fixture", summary="fixture",
                source="fixture", ingestion_id=uuid4(), doc_type="file",
                canonical_id="fixture.txt", relative_path="fixture.txt",
            )
    finally:
        ownership_check.reset(token)
    session.commit.assert_not_called()
