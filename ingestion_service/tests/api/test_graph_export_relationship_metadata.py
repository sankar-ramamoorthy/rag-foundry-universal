# ingestion_service/tests/api/test_graph_export_relationship_metadata.py
"""
Issue #220: relationship_metadata (confidence, call_sites, bases, etc.)
must survive db_utils.get_full_graph_for_repo and the
GET /v1/graph/repos/{repo_id} HTTP response, not be stripped as it
previously was -- the first export step discarded it even though it was
always correctly persisted to DocumentRelationship.relationship_metadata.
"""

import uuid

from fastapi import FastAPI
from fastapi.testclient import TestClient
import pytest

import src.core.models  # noqa: F401  (register IngestionRequest for FK metadata)
from shared.models.document_node import DocumentNode
from src.api.v1 import graph as graph_module
from src.core import db_utils
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
    app.include_router(graph_module.router)  # router already carries prefix="/graph"
    return TestClient(app)


def _persist_call_edge_with_metadata(session, repo_id, ingestion_id):
    StatusManager(session).create_request(
        ingestion_id=uuid.UUID(ingestion_id),
        source_type="repo",
        metadata={},
        repo_id=repo_id,
    )
    StatusManager(session).mark_running(uuid.UUID(ingestion_id))
    StatusManager(session).mark_completed(uuid.UUID(ingestion_id))
    CodebaseGraphPersistence(session=session).persist_graph(
        repo_id=repo_id,
        nodes=[
            {
                "canonical_id": "caller.py#outer",
                "relative_path": "caller.py",
                "title": "outer",
                "doc_type": "code",
                "source": "caller.py",
                "summary": "",
                "text": "def outer(): inner()",
                "ingestion_id": ingestion_id,
            },
            {
                "canonical_id": "callee.py#inner",
                "relative_path": "callee.py",
                "title": "inner",
                "doc_type": "code",
                "source": "callee.py",
                "summary": "",
                "text": "def inner(): pass",
                "ingestion_id": ingestion_id,
            },
        ],
        relationships=[
            {
                "from_canonical_id": "caller.py#outer",
                "to_canonical_id": "callee.py#inner",
                "relation_type": "CALL",
                "relationship_metadata": {
                    "confidence": 1.0,
                    "call_sites": [7],
                    "count": 1,
                },
            },
        ],
    )


def test_get_full_graph_for_repo_includes_relationship_metadata(repo_id):
    ingestion_id = str(uuid.uuid4())
    Session = get_sessionmaker()
    with Session() as s:
        _persist_call_edge_with_metadata(s, repo_id, ingestion_id)

    graph = db_utils.get_full_graph_for_repo(repo_id)
    edges = graph["relationships"]["caller.py#outer"]
    call_edge = next(e for e in edges if e["relation_type"] == "CALL")
    assert call_edge["relationship_metadata"] == {
        "confidence": 1.0,
        "call_sites": [7],
        "count": 1,
    }


def test_full_graph_http_response_includes_relationship_metadata(client, repo_id):
    ingestion_id = str(uuid.uuid4())
    Session = get_sessionmaker()
    with Session() as s:
        _persist_call_edge_with_metadata(s, repo_id, ingestion_id)

    response = client.get(f"/graph/repos/{repo_id}")
    assert response.status_code == 200
    body = response.json()
    edges = body["relationships"]["caller.py#outer"]
    call_edge = next(e for e in edges if e["relation_type"] == "CALL")
    assert call_edge["relationship_metadata"] == {
        "confidence": 1.0,
        "call_sites": [7],
        "count": 1,
    }
