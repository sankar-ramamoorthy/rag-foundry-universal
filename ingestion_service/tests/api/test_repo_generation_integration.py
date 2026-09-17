# ingestion_service/tests/api/test_repo_generation_integration.py
"""
Issue #168 (WP-R5): GET /v1/repos/{repo_id}/generation against real
Postgres, through the actual FastAPI route (not just db_utils directly,
as test_repo_lifecycle.py already covers) -- proves the HTTP contract
rag_orchestrator's graph cache depends on, end to end at the ingestion_
service boundary. A full two-service HTTP round trip (a live
rag_orchestrator process actually calling a live ingestion_service) is not
covered here or anywhere in CI yet -- disclosed, not claimed.
"""
import uuid

from fastapi import FastAPI
from fastapi.testclient import TestClient
import pytest

import src.core.models  # noqa: F401  (register IngestionRequest for FK metadata)
from shared.models.document_node import DocumentNode
from src.api.v1 import repos as repos_module
from src.core.database_session import get_sessionmaker
from src.core.status_manager import StatusManager
from src.core.codebase.codebase_persistence import CodebaseGraphPersistence

pytestmark = [pytest.mark.integration, pytest.mark.docker]


@pytest.fixture()
def repo_id():
    rid = str(uuid.uuid4())
    yield rid
    Session = get_sessionmaker()
    with Session() as s:
        s.query(DocumentNode).filter_by(repo_id=rid).delete(synchronize_session=False)
        s.commit()
    with Session() as s:
        from src.core.models import IngestionRequest
        s.query(IngestionRequest).filter_by(repo_id=rid).delete(
            synchronize_session=False,
        )
        s.commit()


@pytest.fixture()
def client():
    app = FastAPI()
    app.include_router(repos_module.router)
    return TestClient(app)


def _make_ingestion(session, repo_id, status="accepted"):
    ing = uuid.uuid4()
    StatusManager(session).create_request(
        ingestion_id=ing, source_type="repo", metadata={}, repo_id=repo_id,
    )
    if status == "completed":
        StatusManager(session).mark_running(ing)
        StatusManager(session).mark_completed(ing)
    elif status == "running":
        StatusManager(session).mark_running(ing)
    return ing


def _persist_one_node(session, repo_id, ingestion_id, tag):
    CodebaseGraphPersistence(session=session).persist_graph(
        repo_id=repo_id,
        nodes=[{
            "canonical_id": f"pkg/{tag}.py", "relative_path": f"pkg/{tag}.py",
            "title": tag, "doc_type": "code", "source": f"pkg/{tag}.py",
            "summary": "", "text": f"def {tag}(): pass",
            "ingestion_id": ingestion_id,
        }],
        relationships=[],
    )


def test_unknown_repo_reports_unknown(client, repo_id):
    response = client.get(f"/repos/{repo_id}/generation")

    assert response.status_code == 200
    body = response.json()
    assert body == {
        "repo_id": repo_id, "ingestion_id": None, "generation_status": "unknown",
    }


def test_ready_repo_reports_its_ingestion_id(client, repo_id):
    Session = get_sessionmaker()
    with Session() as s:
        ing = _make_ingestion(s, repo_id, status="completed")
        _persist_one_node(s, repo_id, ing, "a")

    body = client.get(f"/repos/{repo_id}/generation").json()

    assert body["generation_status"] == "ready"
    assert body["ingestion_id"] == str(ing)


def test_rebuild_in_progress_reports_building_with_no_ingestion_id(
    client, repo_id,
):
    """The exact scenario the graph cache uses this endpoint to detect:
    a completed generation exists, a rebuild starts and its graph-build
    step has already run (document_nodes now belongs to the new attempt),
    but it hasn't reached completed yet."""
    Session = get_sessionmaker()
    with Session() as s:
        _make_ingestion(s, repo_id, status="completed")
    with Session() as s:
        ing2 = _make_ingestion(s, repo_id, status="running")
        _persist_one_node(s, repo_id, ing2, "new")

    body = client.get(f"/repos/{repo_id}/generation").json()

    assert body["generation_status"] == "building"
    assert body["ingestion_id"] is None


def test_reingest_under_same_repo_id_is_observed_via_the_endpoint(
    client, repo_id,
):
    """#168's core acceptance criterion, exercised through the real HTTP
    route: re-ingest a changed edge under the same repo_id and the
    generation endpoint (what a warm worker's cache would poll) must
    report the new ingestion_id, not the old one."""
    Session = get_sessionmaker()
    with Session() as s:
        ing1 = _make_ingestion(s, repo_id, status="completed")
        _persist_one_node(s, repo_id, ing1, "old")

    first = client.get(f"/repos/{repo_id}/generation").json()
    assert first["ingestion_id"] == str(ing1)

    with Session() as s:
        ing2 = _make_ingestion(s, repo_id, status="completed")
        _persist_one_node(s, repo_id, ing2, "new")

    second = client.get(f"/repos/{repo_id}/generation").json()
    assert second["ingestion_id"] == str(ing2)
    assert second["ingestion_id"] != first["ingestion_id"]
