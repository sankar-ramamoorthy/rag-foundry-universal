# ingestion_service/tests/core/codebase/test_persist_graph_upsert.py
"""
Foundational persistence-invariant tests for issue #196 (Phase 2).

persist_graph moves from delete-all-then-insert-all to an upsert-by-
(repo_id, canonical_id) model: a canonical_id present across two
persist_graph calls MUST keep the same document_id (R1, plan.md's
central risk), so vectors/relationships tied to that row survive a
re-ingestion instead of being cascade-deleted and re-created.

Run against docker-compose.test.yml Postgres, e.g.:
  DATABASE_URL=postgresql://...@localhost:5433/ingestion_test \
    ../.venv/Scripts/python.exe -m pytest \
    tests/core/codebase/test_persist_graph_upsert.py -m integration
"""
import uuid

import pytest
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError

from src.core.models import IngestionRequest
from shared.models.document_node import DocumentNode
from shared.models.document_relationship import DocumentRelationship
from src.core.database_session import get_sessionmaker
from src.core.status_manager import StatusManager
from src.core.codebase.codebase_persistence import CodebaseGraphPersistence

pytestmark = [pytest.mark.integration, pytest.mark.docker]


@pytest.fixture()
def ingestion_ids():
    """Two ingestion_requests rows (old generation, new generation)."""
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


def _node(ingestion_id, canonical_id, title="t", text="pass"):
    return {
        "canonical_id": canonical_id,
        "relative_path": canonical_id,
        "title": title,
        "doc_type": "code",
        "source": canonical_id,
        "summary": "",
        "text": text,
        "ingestion_id": ingestion_id,
    }


def _persist(repo_id, nodes, relationships=None):
    Session = get_sessionmaker()
    with Session() as s:
        return CodebaseGraphPersistence(session=s).persist_graph(
            repo_id=repo_id, nodes=nodes, relationships=relationships or []
        )


def _document_id(repo_id, canonical_id):
    Session = get_sessionmaker()
    with Session() as s:
        row = (
            s.query(DocumentNode)
            .filter_by(repo_id=repo_id, canonical_id=canonical_id)
            .one_or_none()
        )
        return row.document_id if row else None


# ingestion_service.vector_chunks is the live table (F-15); the ORM class
# shared.models.vector_chunk.VectorChunk maps to a stale/legacy "vectors"
# table with no document_id column at all — disclosed pre-existing drift
# (DOCS/audit/01-Codebase-Audit-Findings.md), out of scope for #196. Use
# raw SQL against the real table instead.

def _insert_vector_chunk(session, document_id, ingestion_id, chunk_index=0):
    session.execute(
        text(
            "INSERT INTO ingestion_service.vector_chunks "
            "(document_id, chunk_id, chunk_index, chunk_strategy, "
            "chunk_text, ingestion_id, vector) "
            "VALUES (:document_id, :chunk_id, :chunk_index, "
            ":chunk_strategy, :chunk_text, :ingestion_id, "
            "CAST(:vector AS vector))"
        ),
        {
            "document_id": document_id,
            "chunk_id": str(uuid.uuid4()),
            "chunk_index": chunk_index,
            "chunk_strategy": "whole_file",
            "chunk_text": "pass",
            "ingestion_id": ingestion_id,
            "vector": "[" + ",".join(["0.0"] * 1024) + "]",
        },
    )


def _count_vector_chunks(document_id):
    Session = get_sessionmaker()
    with Session() as s:
        return s.execute(
            text(
                "SELECT count(*) FROM ingestion_service.vector_chunks "
                "WHERE document_id = :document_id"
            ),
            {"document_id": document_id},
        ).scalar()


# ---------------------------------------------------------------------
# T005: document_id stability across generations
# ---------------------------------------------------------------------

def test_reused_canonical_id_keeps_same_document_id(ingestion_ids, repo_id):
    old_id, new_id = ingestion_ids
    _persist(repo_id, [_node(old_id, "pkg/a.py")])
    first_doc_id = _document_id(repo_id, "pkg/a.py")
    assert first_doc_id is not None

    _persist(repo_id, [_node(new_id, "pkg/a.py", title="updated")])
    second_doc_id = _document_id(repo_id, "pkg/a.py")

    assert second_doc_id == first_doc_id, (
        "document_id must be stable across generations for a canonical_id "
        "whose row survives (R1) — reused rows must be updated in place, "
        "not deleted and reinserted"
    )


# ---------------------------------------------------------------------
# T006: genuinely removed canonical_ids are deleted, cascade fires
# ---------------------------------------------------------------------

def test_removed_canonical_id_is_deleted_with_cascade(ingestion_ids, repo_id):
    old_id, new_id = ingestion_ids
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
    removed_doc_id = _document_id(repo_id, "pkg/b.py")
    assert removed_doc_id is not None

    Session = get_sessionmaker()
    with Session() as s:
        _insert_vector_chunk(s, removed_doc_id, old_id)
        s.commit()
    assert _count_vector_chunks(removed_doc_id) == 1

    _persist(repo_id, [_node(new_id, "pkg/a.py")])

    assert _document_id(repo_id, "pkg/b.py") is None, (
        "canonical_id absent from the new node set must be deleted"
    )

    Session = get_sessionmaker()
    with Session() as s:
        assert (
            s.query(DocumentRelationship)
            .filter(
                (DocumentRelationship.from_document_id == removed_doc_id)
                | (DocumentRelationship.to_document_id == removed_doc_id)
            )
            .count()
            == 0
        ), "relationships referencing the deleted node must be gone (cascade)"
    assert _count_vector_chunks(removed_doc_id) == 0, (
        "vectors referencing the deleted node must be gone (cascade)"
    )


# ---------------------------------------------------------------------
# T007: a reused document_id's vectors survive the second persist_graph
# ---------------------------------------------------------------------

def test_reused_document_id_keeps_vectors_fk_valid(ingestion_ids, repo_id):
    old_id, new_id = ingestion_ids
    _persist(repo_id, [_node(old_id, "pkg/a.py")])
    doc_id = _document_id(repo_id, "pkg/a.py")

    Session = get_sessionmaker()
    with Session() as s:
        _insert_vector_chunk(s, doc_id, old_id)
        s.commit()

    _persist(repo_id, [_node(new_id, "pkg/a.py", title="updated")])

    assert _count_vector_chunks(doc_id) == 1, (
        "a vector row against a reused document_id must survive the "
        "second persist_graph call (FK intact, not cascade-deleted)"
    )


# ---------------------------------------------------------------------
# T008: a mid-transaction failure leaves the previous generation intact
# ---------------------------------------------------------------------

def test_failed_upsert_leaves_previous_generation_unchanged(ingestion_ids, repo_id):
    old_id, new_id = ingestion_ids
    _persist(repo_id, [_node(old_id, "pkg/a.py"), _node(old_id, "pkg/b.py")])
    before_a = _document_id(repo_id, "pkg/a.py")
    before_b = _document_id(repo_id, "pkg/b.py")

    poisoned = [_node(new_id, "pkg/a.py", title="v2")]
    duplicate = dict(poisoned[0])
    poisoned.append(duplicate)  # duplicate canonical_id -> forces failure

    with pytest.raises(SQLAlchemyError):
        _persist(repo_id, poisoned)

    assert _document_id(repo_id, "pkg/a.py") == before_a
    assert _document_id(repo_id, "pkg/b.py") == before_b

    Session = get_sessionmaker()
    with Session() as s:
        row = s.query(DocumentNode).filter_by(document_id=before_a).one()
        assert row.title == "t", (
            "a failed upsert must roll back completely, leaving the "
            "previous generation's rows completely unchanged"
        )
