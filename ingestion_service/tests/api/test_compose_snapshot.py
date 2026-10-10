"""The Compose read API serves only the requested ready generation."""

from fastapi import FastAPI
from fastapi.testclient import TestClient
import pytest

from src.api.v1 import repos

pytestmark = pytest.mark.unit


def _client(monkeypatch, current="g1", summary=None):
    monkeypatch.setattr(repos.db_utils, "resolve_current_generation", lambda _: current)
    monkeypatch.setattr(repos.db_utils, "generation_status", lambda _: "ready")
    monkeypatch.setattr(
        repos.db_utils,
        "get_structural_summary",
        lambda _: summary if summary is not None else {},
    )
    monkeypatch.setattr(
        repos.db_utils, "generation_lineage", lambda _: {"commit_sha": "a" * 40}
    )
    app = FastAPI()
    app.include_router(repos.router, prefix="/v1")
    return TestClient(app)


def test_pinned_compose_snapshot_http(monkeypatch):
    documents = {
        "docker-compose.yml": {
            "sha256": "b" * 64,
            "content": {"services": {"app": {
                "image": "busybox",
                "environment": {
                    "DATABASE_URL": "postgresql://user:secret@postgres:5432/db",
                    "POSTGRES_PASSWORD": "secret",
                },
            }}},
        }
    }
    client = _client(monkeypatch, summary={"compose_documents": documents})
    response = client.get("/v1/repos/r1/compose-snapshot?generation_id=g1")
    assert response.status_code == 200
    returned = response.json()["compose_documents"]["docker-compose.yml"]
    assert returned["sha256"] == "b" * 64
    environment = returned["content"]["services"]["app"]["environment"]
    assert environment == {"DATABASE_URL": "postgresql://postgres"}
    assert "secret" not in response.text
    assert response.json()["commit_sha"] == "a" * 40


def test_snapshot_rejects_generation_mismatch_and_missing_content(monkeypatch):
    client = _client(monkeypatch)
    assert client.get(
        "/v1/repos/r1/compose-snapshot?generation_id=old"
    ).status_code == 409
    assert client.get(
        "/v1/repos/r1/compose-snapshot?generation_id=g1"
    ).status_code == 404


def test_snapshot_rejects_generation_change_during_read(monkeypatch):
    client = _client(monkeypatch, summary={"compose_documents": {}})
    generations = iter(("g1", "g2"))
    monkeypatch.setattr(
        repos.db_utils, "resolve_current_generation", lambda _: next(generations)
    )
    response = client.get("/v1/repos/r1/compose-snapshot?generation_id=g1")
    assert response.status_code == 409


def test_snapshot_rejects_invalid_summary_format(monkeypatch):
    client = _client(monkeypatch, summary={"compose_documents": []})
    response = client.get("/v1/repos/r1/compose-snapshot?generation_id=g1")
    assert response.status_code == 503
