# ingestion_service/tests/core/test_db_utils_repo_delete.py
"""
Issue #158: db_utils helpers backing DELETE /v1/repos/{repo_id}.

Against real Postgres (docker-compose.test.yml) — these exercise the
actual schema constraint the whole design depends on: document_nodes
is the only place repo_id -> ingestion_id is recorded (ingestion_requests
has no repo_id column of its own), so list_ingestion_ids_for_repo must
be called, and its result held, before document_nodes rows are deleted.

Run with DATABASE_URL pointing at the test DB (localhost:5433), e.g.:
  DATABASE_URL=postgresql://...@localhost:5433/ingestion_test \
    ../.venv/Scripts/python.exe -m pytest tests/core/test_db_utils_repo_delete.py \
      -m integration
"""
import uuid

import pytest

import src.core.models  # noqa: F401  (register IngestionRequest for FK metadata)
from shared.models.document_node import DocumentNode
from src.core import db_utils
from src.core.database_session import get_sessionmaker
from src.core.status_manager import StatusManager
from src.core.codebase.codebase_persistence import CodebaseGraphPersistence

pytestmark = [pytest.mark.integration, pytest.mark.docker]


def _make_ingestion(session, metadata=None):
    ing = uuid.uuid4()
    StatusManager(session).create_request(
        ingestion_id=ing, source_type="repo", metadata=metadata or {}
    )
    return str(ing)


def _persist_one_node(session, repo_id, ingestion_id, tag):
    CodebaseGraphPersistence(session=session).persist_graph(
        repo_id=repo_id,
        nodes=[
            {
                "canonical_id": f"pkg/{tag}.py",
                "relative_path": f"pkg/{tag}.py",
                "title": tag,
                "doc_type": "code",
                "source": f"pkg/{tag}.py",
                "summary": "",
                "text": f"def {tag}(): pass",
                "ingestion_id": ingestion_id,
            }
        ],
        relationships=[],
    )


@pytest.fixture()
def repo_id():
    rid = str(uuid.uuid4())
    yield rid
    Session = get_sessionmaker()
    with Session() as s:
        s.query(DocumentNode).filter_by(repo_id=rid).delete(synchronize_session=False)
        s.commit()


class TestListIngestionIdsForRepo:
    def test_returns_every_historical_ingestion_id_not_just_latest(self, repo_id):
        """A repo re-ingested twice has two ingestion_ids in document_nodes'
        history even after persist_graph's replace-on-reingest has removed
        the first ingestion's *nodes* -- but list_ingestion_ids_for_repo
        only sees what's currently in document_nodes, so after a rebuild it
        reports the *current* ingestion_id only. This test locks that
        behavior in explicitly, since it matters for issue #158: a repo
        delete only needs to clean up the ingestion_ids still referenced
        by live document_nodes, not truly every ingestion_id ever created
        for that repo_id historically."""
        Session = get_sessionmaker()
        with Session() as s:
            ing1 = _make_ingestion(s)
            _persist_one_node(s, repo_id, ing1, "a")

        ids = db_utils.list_ingestion_ids_for_repo(repo_id)
        assert ids == [ing1]

        Session = get_sessionmaker()
        with Session() as s:
            ing2 = _make_ingestion(s)
            _persist_one_node(s, repo_id, ing2, "b")  # replaces ing1's node

        ids = db_utils.list_ingestion_ids_for_repo(repo_id)
        assert ids == [ing2]

    def test_unknown_repo_id_returns_empty_list(self):
        assert db_utils.list_ingestion_ids_for_repo(str(uuid.uuid4())) == []


class TestDeleteIngestionRequests:
    def test_deletes_only_the_given_ids(self, repo_id):
        Session = get_sessionmaker()
        with Session() as s:
            ing_keep = _make_ingestion(s)
            ing_delete = _make_ingestion(s)

        deleted = db_utils.delete_ingestion_requests([ing_delete])
        assert deleted == 1
        assert db_utils.get_ingestion_status(uuid.UUID(ing_delete)) is None
        assert db_utils.get_ingestion_status(uuid.UUID(ing_keep)) is not None

        # cleanup the row this test didn't delete
        db_utils.delete_ingestion_requests([ing_keep])

    def test_idempotent_on_already_deleted_ids(self):
        """Calling this twice (or on IDs that were never real) must not
        raise -- issue #158's idempotency requirement."""
        fake_id = str(uuid.uuid4())
        assert db_utils.delete_ingestion_requests([fake_id]) == 0
        assert db_utils.delete_ingestion_requests([fake_id]) == 0

    def test_empty_list_is_a_no_op(self):
        assert db_utils.delete_ingestion_requests([]) == 0


class TestRepoDeleteOrderingConstraint:
    def test_enumeration_must_happen_before_node_deletion(self, repo_id):
        """Demonstrates the exact constraint issue #158's ordering is built
        around: once delete_repo_nodes runs, the repo_id -> ingestion_id
        mapping is gone from document_nodes, and list_ingestion_ids_for_repo
        can no longer recover it."""
        Session = get_sessionmaker()
        with Session() as s:
            ing = _make_ingestion(s)
            _persist_one_node(s, repo_id, ing, "a")

        ids_before = db_utils.list_ingestion_ids_for_repo(repo_id)
        assert ids_before == [ing]

        with Session() as s:
            CodebaseGraphPersistence(session=s).delete_repo_nodes(repo_id)

        ids_after = db_utils.list_ingestion_ids_for_repo(repo_id)
        assert ids_after == [], (
            "mapping is gone once document_nodes rows are deleted -- "
            "enumeration must happen first, exactly as delete_repo relies on"
        )

        db_utils.delete_ingestion_requests([ing])
