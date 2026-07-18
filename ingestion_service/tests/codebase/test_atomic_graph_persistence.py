# ingestion_service/tests/codebase/test_atomic_graph_persistence.py
"""
F-09/F-06 (WP-S3): transactional, bulk graph persistence + per-repo lock.

Acceptance criteria covered (against docker-compose.test.yml Postgres):
- a failed rebuild rolls back completely: the previous graph is intact;
- delete + nodes + relationships commit atomically in one transaction;
- concurrent rebuilds of the same repo serialize on the advisory lock
  and can never interleave destructively (final state is exactly one
  full version, never a mix);
- persistence is bulk: statement count is constant-ish, not per-edge.

Run with DATABASE_URL pointing at the test DB (localhost:5433), e.g.:
  DATABASE_URL=postgresql://...@localhost:5433/ingestion_test \
    ../.venv/Scripts/python.exe -m pytest tests/codebase/ -m integration
"""
import threading
import uuid

import pytest
from sqlalchemy import event
from sqlalchemy.exc import IntegrityError

import src.core.models  # noqa: F401  (register IngestionRequest for FK metadata)
from shared.models.document_node import DocumentNode
from shared.models.document_relationship import DocumentRelationship
from src.core.database_session import get_engine, get_sessionmaker
from src.core.status_manager import StatusManager
from src.core.codebase.codebase_persistence import CodebaseGraphPersistence

pytestmark = [pytest.mark.integration, pytest.mark.docker]


@pytest.fixture(scope="module")
def ingestion_id():
    """One ingestion_requests row all test nodes can point at (FK)."""
    Session = get_sessionmaker()
    with Session() as s:
        ing = uuid.uuid4()
        StatusManager(s).create_request(
            ingestion_id=ing, source_type="repo", metadata={}
        )
        yield str(ing)


@pytest.fixture()
def repo_id():
    """Fresh repo namespace per test; cleaned up afterwards."""
    rid = str(uuid.uuid4())
    yield rid
    Session = get_sessionmaker()
    with Session() as s:
        s.query(DocumentNode).filter_by(repo_id=rid).delete(
            synchronize_session=False
        )
        s.commit()


def _nodes(ingestion_id, count, tag):
    return [
        {
            "canonical_id": f"pkg/{tag}{i}.py",
            "relative_path": f"pkg/{tag}{i}.py",
            "title": tag,
            "doc_type": "code",
            "source": f"pkg/{tag}{i}.py",
            "summary": "",
            "text": f"def {tag}{i}(): pass",
            "ingestion_id": ingestion_id,
        }
        for i in range(count)
    ]


def _chain_rels(nodes):
    return [
        {
            "from_canonical_id": a["canonical_id"],
            "to_canonical_id": b["canonical_id"],
            "relation_type": "CALL",
            "relationship_metadata": {},
        }
        for a, b in zip(nodes, nodes[1:])
    ]


def _graph_state(repo_id):
    """Return ({canonical_id: title}, relationship_count) for the repo."""
    Session = get_sessionmaker()
    with Session() as s:
        rows = (
            s.query(DocumentNode.canonical_id, DocumentNode.title,
                    DocumentNode.document_id)
            .filter(DocumentNode.repo_id == repo_id)
            .all()
        )
        doc_ids = [r.document_id for r in rows]
        rel_count = (
            s.query(DocumentRelationship)
            .filter(DocumentRelationship.from_document_id.in_(doc_ids))
            .count()
            if doc_ids
            else 0
        )
        return {r.canonical_id: r.title for r in rows}, rel_count


def _persist(repo_id, nodes, relationships):
    Session = get_sessionmaker()
    with Session() as s:
        return CodebaseGraphPersistence(session=s).persist_graph(
            repo_id=repo_id, nodes=nodes, relationships=relationships
        )


# ---------------------------------------------------------------------
# Atomic commit of nodes + relationships
# ---------------------------------------------------------------------

def test_persist_graph_round_trip(repo_id, ingestion_id):
    nodes = _nodes(ingestion_id, 5, "a")
    rels = _chain_rels(nodes)
    rels.append(
        {
            "from_canonical_id": "pkg/a0.py",
            "to_canonical_id": "pkg/ghost.py",  # unknown endpoint
            "relation_type": "CALL",
            "relationship_metadata": {},
        }
    )

    stats = _persist(repo_id, nodes, rels)

    assert stats["nodes"] == 5
    assert stats["relationships"] == 4
    assert stats["skipped_relationships"] == 1

    state, rel_count = _graph_state(repo_id)
    assert set(state) == {f"pkg/a{i}.py" for i in range(5)}
    assert rel_count == 4


def test_rebuild_replaces_previous_graph(repo_id, ingestion_id):
    _persist(repo_id, _nodes(ingestion_id, 5, "a"), [])
    v2 = _nodes(ingestion_id, 3, "b")
    stats = _persist(repo_id, v2, _chain_rels(v2))

    assert stats["deleted"] == 5
    state, rel_count = _graph_state(repo_id)
    assert set(state) == {f"pkg/b{i}.py" for i in range(3)}
    assert rel_count == 2


def test_failed_rebuild_preserves_previous_graph(repo_id, ingestion_id):
    v1 = _nodes(ingestion_id, 4, "a")
    _persist(repo_id, v1, _chain_rels(v1))

    poisoned = _nodes(ingestion_id, 3, "b")
    poisoned.append(dict(poisoned[0]))  # duplicate canonical_id -> uq violation

    with pytest.raises(IntegrityError):
        _persist(repo_id, poisoned, [])

    state, rel_count = _graph_state(repo_id)
    assert set(state) == {f"pkg/a{i}.py" for i in range(4)}, (
        "failed rebuild must leave the previous graph intact"
    )
    assert rel_count == 3


# ---------------------------------------------------------------------
# Per-repo advisory lock: concurrent rebuilds never interleave
# ---------------------------------------------------------------------

def test_concurrent_rebuilds_never_interleave(repo_id, ingestion_id):
    version_a = _nodes(ingestion_id, 6, "a")
    version_b = _nodes(ingestion_id, 9, "b")
    errors = []

    def worker(nodes):
        try:
            _persist(repo_id, nodes, _chain_rels(nodes))
        except Exception as exc:  # noqa: BLE001 - recorded for the assert
            errors.append(exc)

    for _ in range(3):  # repeat to give interleaving a chance
        barrier = threading.Barrier(2)

        def run(nodes):
            barrier.wait()
            worker(nodes)

        threads = [
            threading.Thread(target=run, args=(version_a,)),
            threading.Thread(target=run, args=(version_b,)),
        ]
        for t in threads:
            t.start()
        for t in threads:
            t.join(timeout=30)

        assert not errors, errors
        state, rel_count = _graph_state(repo_id)
        titles = set(state.values())
        assert titles in ({"a"}, {"b"}), f"interleaved graph: {state}"
        if titles == {"a"}:
            assert len(state) == 6 and rel_count == 5
        else:
            assert len(state) == 9 and rel_count == 8


# ---------------------------------------------------------------------
# Bulk persistence: statements scale with batches, not edges
# ---------------------------------------------------------------------

def test_persist_graph_statement_count_is_bulk(repo_id, ingestion_id):
    nodes = _nodes(ingestion_id, 50, "a")
    rels = _chain_rels(nodes)  # 49 edges
    statements = []

    def counter(conn, cursor, statement, parameters, context, executemany):
        statements.append(statement)

    engine = get_engine()
    event.listen(engine, "before_cursor_execute", counter)
    try:
        _persist(repo_id, nodes, rels)
    finally:
        event.remove(engine, "before_cursor_execute", counter)

    # lock + delete + 1 node batch + 1 relationship batch (+ session noise);
    # the old path issued 3 statements per edge (~150 here).
    assert len(statements) <= 10, (
        f"{len(statements)} statements for 50 nodes / 49 edges:\n"
        + "\n".join(statements[:20])
    )
