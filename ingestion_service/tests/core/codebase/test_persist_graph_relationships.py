# ingestion_service/tests/core/codebase/test_persist_graph_relationships.py
"""
T009 (issue #196, Phase 2 Foundational): repo-scoped relationship replace.

A document_relationships row from a prior persist_graph call, touching a
node that is *reused unchanged* in the next call, must be removed and
replaced by that call's freshly supplied relationship set — proving the
repo_id-scoped relationship replace (research.md R2) doesn't rely on
node-cascade to clean up edges (a reused node is never deleted, so
cascade never fires for it).

Run against docker-compose.test.yml Postgres, e.g.:
  DATABASE_URL=postgresql://...@localhost:5433/ingestion_test \
    ../.venv/Scripts/python.exe -m pytest \
    tests/core/codebase/test_persist_graph_relationships.py -m integration
"""
import uuid

import pytest

from src.core.models import IngestionRequest
from shared.models.document_node import DocumentNode
from shared.models.document_relationship import DocumentRelationship
from src.core.database_session import get_sessionmaker
from src.core.status_manager import StatusManager
from src.core.codebase.codebase_persistence import CodebaseGraphPersistence

pytestmark = [pytest.mark.integration, pytest.mark.docker]


@pytest.fixture()
def ingestion_ids():
    Session = get_sessionmaker()
    with Session() as s:
        old_id = uuid.uuid4()
        new_id = uuid.uuid4()
        StatusManager(s).create_request(
            ingestion_id=old_id, source_type="repo", metadata={}
        )
        StatusManager(s).create_request(
            ingestion_id=new_id, source_type="repo", metadata={}
        )
        yield str(old_id), str(new_id)
        s.query(IngestionRequest).filter(
            IngestionRequest.ingestion_id.in_([old_id, new_id])
        ).delete(synchronize_session=False)
        s.commit()


@pytest.fixture()
def repo_id():
    rid = str(uuid.uuid4())
    yield rid
    Session = get_sessionmaker()
    with Session() as s:
        s.query(DocumentNode).filter_by(repo_id=rid).delete(
            synchronize_session=False
        )
        s.commit()


def _node(ingestion_id, canonical_id):
    return {
        "canonical_id": canonical_id,
        "relative_path": canonical_id,
        "title": canonical_id,
        "doc_type": "code",
        "source": canonical_id,
        "summary": "",
        "text": "pass",
        "ingestion_id": ingestion_id,
    }


def _persist(repo_id, nodes, relationships):
    Session = get_sessionmaker()
    with Session() as s:
        return CodebaseGraphPersistence(session=s).persist_graph(
            repo_id=repo_id, nodes=nodes, relationships=relationships
        )


def _document_id(repo_id, canonical_id):
    Session = get_sessionmaker()
    with Session() as s:
        row = (
            s.query(DocumentNode)
            .filter_by(repo_id=repo_id, canonical_id=canonical_id)
            .one()
        )
        return row.document_id


def _relation_types(repo_id, document_id):
    Session = get_sessionmaker()
    with Session() as s:
        rows = (
            s.query(DocumentRelationship.relation_type)
            .filter(
                (DocumentRelationship.from_document_id == document_id)
                | (DocumentRelationship.to_document_id == document_id)
            )
            .all()
        )
        return {r.relation_type for r in rows}


def test_stale_relationship_on_reused_node_is_replaced(ingestion_ids, repo_id):
    old_id, new_id = ingestion_ids
    # Generation 1: a.py CALLs b.py.
    _persist(
        repo_id,
        [_node(old_id, "pkg/a.py"), _node(old_id, "pkg/b.py")],
        [
            {
                "from_canonical_id": "pkg/a.py",
                "to_canonical_id": "pkg/b.py",
                "relation_type": "CALL",
                "relationship_metadata": {},
            }
        ],
    )
    a_doc_id = _document_id(repo_id, "pkg/a.py")
    assert _relation_types(repo_id, a_doc_id) == {"CALL"}

    # Generation 2: both nodes reused unchanged (same content), but the
    # freshly resolved graph no longer has the CALL edge (e.g. the call
    # site itself was removed from a different file, or resolution
    # changed) — DEFINES replaces it instead.
    _persist(
        repo_id,
        [_node(new_id, "pkg/a.py"), _node(new_id, "pkg/b.py")],
        [
            {
                "from_canonical_id": "pkg/a.py",
                "to_canonical_id": "pkg/b.py",
                "relation_type": "DEFINES",
                "relationship_metadata": {},
            }
        ],
    )

    assert _document_id(repo_id, "pkg/a.py") == a_doc_id, (
        "both nodes are unchanged, so document_id must be reused (R1)"
    )
    assert _relation_types(repo_id, a_doc_id) == {"DEFINES"}, (
        "the stale CALL relationship must be gone even though neither "
        "endpoint node was deleted — relationship replace is repo_id-"
        "scoped, not dependent on node-cascade (R2)"
    )
