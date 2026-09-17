"""#160 real PostgreSQL page isolation, input envelope and generation checks."""

import uuid

import pytest
from sqlalchemy import event

from shared.models.document_node import DocumentNode
from src.core.models import IngestionRequest
from src.core.database_session import get_sessionmaker, get_engine
from src.core.status_manager import StatusManager
from src.core.codebase.codebase_persistence import CodebaseGraphPersistence


pytestmark = [pytest.mark.integration, pytest.mark.docker]


@pytest.fixture
def corpus():
    repo, attempt = str(uuid.uuid4()), uuid.uuid4()
    factory = get_sessionmaker()
    with factory() as session:
        StatusManager(session).create_request(
            ingestion_id=attempt,
            source_type="repo",
            metadata={},
        )
        nodes = [
            {
                "canonical_id": f"{i}.py",
                "relative_path": f"{i}.py",
                "text": value,
                "ingestion_id": str(attempt),
            }
            for i, value in enumerate([None, "", "\t\n\u2003", "snow 雪", "code"])
        ]
        CodebaseGraphPersistence(session).persist_graph(repo, nodes, [])
    yield repo, str(attempt), factory
    with factory() as session:
        session.query(DocumentNode).filter_by(repo_id=repo).delete(
            synchronize_session=False
        )
        session.query(IngestionRequest).filter_by(ingestion_id=attempt).delete()
        session.commit()


def pages(persistence, repo, attempt, **kwargs):
    return persistence.iter_artifact_pages(
        repo,
        attempt,
        page_size=2,
        max_artifact_bytes=20,
        expected_nodes=5,
        **kwargs,
    )


def test_pages_are_narrow_complete_and_generation_scoped(corpus):
    repo, attempt, factory = corpus
    with factory() as session:
        pager = pages(CodebaseGraphPersistence(session), repo, attempt)
        result = list(pager)
        assert [len(page) for page in result] == [2, 2, 1]
        rows = [row for page in result for row in page]
        assert len({row.document_id for row in rows}) == 5
        assert {row.canonical_id for row in rows} == {f"{i}.py" for i in range(5)}
        assert sum(bool((row.text or "").strip()) for row in rows) == 2
        assert set(rows[0]._mapping) == {
            "document_id",
            "canonical_id",
            "relative_path",
            "doc_type",
            "text",
        }
        assert not session.identity_map
        with pytest.raises(RuntimeError, match="generation changed"):
            list(pages(CodebaseGraphPersistence(session), repo, str(uuid.uuid4())))


def test_oversize_rejected_before_any_text_projection(corpus):
    repo, attempt, factory = corpus
    with factory() as session:
        session.query(DocumentNode).filter_by(repo_id=repo, canonical_id="4.py").update(
            {DocumentNode.text: "雪" * 7}
        )
        session.commit()
        statements = []

        def capture(conn, cursor, statement, parameters, context, executemany):
            statements.append(statement)

        engine = get_engine()
        event.listen(engine, "before_cursor_execute", capture)
        try:
            with pytest.raises(ValueError, match="4.py is 21 UTF-8 bytes"):
                list(pages(CodebaseGraphPersistence(session), repo, attempt))
        finally:
            event.remove(engine, "before_cursor_execute", capture)
        assert not any("relative_path" in sql for sql in statements)


def test_disappearing_generation_cannot_complete(corpus):
    repo, attempt, factory = corpus
    with factory() as session:
        iterator = pages(CodebaseGraphPersistence(session), repo, attempt)
        assert len(next(iterator)) == 2
        with factory() as writer:
            writer.query(DocumentNode).filter_by(repo_id=repo).delete(
                synchronize_session=False
            )
            writer.commit()
        with pytest.raises(RuntimeError, match="generation changed"):
            list(iterator)


def test_empty_generation_has_no_pages(corpus):
    _, attempt, factory = corpus
    with factory() as session:
        assert (
            list(
                CodebaseGraphPersistence(session).iter_artifact_pages(
                    "absent",
                    attempt,
                    page_size=2,
                    max_artifact_bytes=20,
                    expected_nodes=0,
                )
            )
            == []
        )
