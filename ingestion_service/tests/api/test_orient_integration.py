# ingestion_service/tests/api/test_orient_integration.py
"""
Issue #197 (ORIENT): GET /v1/repos/{repo_id}/orient against real Postgres,
through the actual FastAPI route -- mirrors test_repo_generation_integration.py's
pattern (manually construct generation state, hit the route, assert the
contract), rather than driving a full background-worker ingestion (which
would need a live embedder/Ollama and duplicates what
test_structural_inventory.py already covers for the pure walk/classify/find
logic).
"""

import uuid

from fastapi import FastAPI
from fastapi.testclient import TestClient
import pytest

import src.core.models  # noqa: F401  (register IngestionRequest for FK metadata)
from shared.models.document_node import DocumentNode
from src.api.v1 import orient as orient_module
from src.core import db_utils
from src.core.database_session import get_sessionmaker
from src.core.status_manager import StatusManager
from src.core.codebase.codebase_persistence import CodebaseGraphPersistence
from src.core.codebase.structural_inventory import (
    GapNote,
    ManifestFact,
    ServiceFact,
    StructuralInventory,
)

pytestmark = [pytest.mark.integration, pytest.mark.docker]

SAMPLE_INVENTORY = StructuralInventory(
    languages={"python": 3, "yaml": 1},
    indexed_file_count=3,
    non_indexed_file_count=2,
    manifests=[ManifestFact(kind="pyproject.toml", path="pyproject.toml")],
    services=[
        ServiceFact(
            name="ingestion_service",
            compose_file="docker-compose.yml",
            dockerfile="ingestion_service/Dockerfile",
            container_name="ingestion-service",
            entry_point="uvicorn src.api.v1.main:app",
            entry_point_source="compose.command",
        ),
    ],
    test_dirs=["tests"],
    docs_dirs=["docs"],
    gaps=[
        GapNote(
            category="entry_point",
            path="docker-compose.yml#postgres",
            reason="no command:",
        )
    ],
)


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
    app.include_router(orient_module.router)
    return TestClient(app)


def _make_completed_generation(session, repo_id, commit_sha=None):
    ing = uuid.uuid4()
    StatusManager(session).create_request(
        ingestion_id=ing,
        source_type="repo",
        metadata={},
        repo_id=repo_id,
    )
    CodebaseGraphPersistence(session=session).persist_graph(
        repo_id=repo_id,
        nodes=[
            {
                "canonical_id": "pkg/a.py",
                "relative_path": "pkg/a.py",
                "title": "a",
                "doc_type": "code",
                "source": "pkg/a.py",
                "summary": "",
                "text": "def a(): pass",
                "ingestion_id": str(ing),
            }
        ],
        relationships=[],
    )
    StatusManager(session).mark_running(ing)
    StatusManager(session).record_completion_lineage(
        ing,
        is_incremental=False,
        commit_sha=commit_sha,
    )
    StatusManager(session).mark_completed(ing)
    return ing


def test_no_generation_returns_404(client, repo_id):
    response = client.get(f"/repos/{repo_id}/orient")
    assert response.status_code == 404


def test_generation_predating_orient_returns_409(client, repo_id):
    Session = get_sessionmaker()
    with Session() as s:
        _make_completed_generation(s, repo_id)
        # structural_summary is never set -- simulates a generation
        # ingested before issue #197 shipped.

    response = client.get(f"/repos/{repo_id}/orient")
    assert response.status_code == 409


def test_ready_generation_returns_deterministic_inventory(client, repo_id):
    Session = get_sessionmaker()
    with Session() as s:
        ing = _make_completed_generation(s, repo_id, commit_sha="abc123")
    db_utils.record_structural_summary(ing, SAMPLE_INVENTORY.summary_dict())

    first = client.get(f"/repos/{repo_id}/orient").json()
    second = client.get(f"/repos/{repo_id}/orient").json()

    assert first == second  # deterministic: same generation, same JSON
    assert first["repo_id"] == repo_id
    assert first["ingestion_id"] == str(ing)
    assert first["generation_status"] == "ready"
    assert first["commit_sha"] == "abc123"
    assert first["languages"] == {"python": 3, "yaml": 1}
    assert first["file_counts"] == {"indexed": 3, "non_indexed": 2, "total": 5}
    assert first["manifests"] == [{"kind": "pyproject.toml", "path": "pyproject.toml"}]
    assert first["services"][0]["name"] == "ingestion_service"
    assert first["services"][0]["dockerfile"] == "ingestion_service/Dockerfile"
    assert first["services"][0]["entry_point"] == "uvicorn src.api.v1.main:app"
    assert first["test_dirs"] == ["tests"]
    assert first["docs_dirs"] == ["docs"]
    assert first["heuristic_fields"] == ["test_dirs", "docs_dirs"]
    assert len(first["gaps"]) == 1
    assert first["gaps"][0]["category"] == "entry_point"


def test_reingest_under_same_repo_id_reports_new_generation(client, repo_id):
    """New generation -> new ingestion_id/structural_summary; the old
    generation's ORIENT result is superseded, not merged with the new one
    (#196's invalidation semantics applied to #197's facts)."""
    Session = get_sessionmaker()
    with Session() as s:
        ing1 = _make_completed_generation(s, repo_id)
    db_utils.record_structural_summary(ing1, SAMPLE_INVENTORY.summary_dict())
    first = client.get(f"/repos/{repo_id}/orient").json()
    assert first["ingestion_id"] == str(ing1)

    other_inventory = StructuralInventory(
        languages={"python": 9},
        indexed_file_count=9,
        non_indexed_file_count=0,
        manifests=[],
        services=[],
        test_dirs=[],
        docs_dirs=[],
        gaps=[],
    )
    with Session() as s:
        ing2 = _make_completed_generation(s, repo_id)
    db_utils.record_structural_summary(ing2, other_inventory.summary_dict())

    second = client.get(f"/repos/{repo_id}/orient").json()
    assert second["ingestion_id"] == str(ing2)
    assert second["ingestion_id"] != first["ingestion_id"]
    assert second["languages"] == {"python": 9}
