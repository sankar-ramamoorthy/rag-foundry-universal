"""#161: failures before processing must not strand accepted requests."""

from unittest.mock import MagicMock
from uuid import uuid4

import pytest

from src.api.v1 import ingest


pytestmark = pytest.mark.unit


@pytest.mark.parametrize("failure_point", ["get_settings", "_build_pipeline"])
def test_file_setup_failure_marks_request_failed(monkeypatch, failure_point):
    attempt = uuid4()
    sessions = MagicMock()
    manager = MagicMock()
    monkeypatch.setattr(ingest, "SessionLocal", sessions)
    monkeypatch.setattr(ingest, "StatusManager", lambda session: manager)
    monkeypatch.setattr(
        ingest, failure_point, MagicMock(side_effect=RuntimeError("setup failed"))
    )

    ingest.background_ingest_file(
        ingestion_id=attempt, file_bytes=b"hello", filename="a.txt",
        content_type="text/plain", metadata={},
    )

    manager.mark_failed.assert_called_once_with(attempt, error="setup failed")
    manager.mark_completed.assert_not_called()


def test_file_mark_running_failure_is_handled_in_fresh_session(monkeypatch):
    attempt = uuid4()
    sessions = MagicMock()
    manager = MagicMock()
    manager.mark_running.side_effect = RuntimeError("start failed")
    monkeypatch.setattr(ingest, "SessionLocal", sessions)
    monkeypatch.setattr(ingest, "StatusManager", lambda session: manager)
    monkeypatch.setattr(ingest, "_build_pipeline", MagicMock())

    ingest.background_ingest_file(
        ingestion_id=attempt, file_bytes=b"hello", filename="a.txt",
        content_type="text/plain", metadata={},
    )

    manager.mark_failed.assert_called_once_with(attempt, error="start failed")
    assert sessions.call_count == 2
    manager.mark_completed.assert_not_called()
