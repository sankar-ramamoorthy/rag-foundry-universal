# ingestion_service/tests/core/test_repo_lifecycle.py
"""#166: repo identity independent of document_nodes, repo-scope mutation
lock, retry-safe delete, and generation resolution.

Against real Postgres (docker-compose.test.yml), like test_db_utils_repo_delete.py.
Run with DATABASE_URL pointing at the test DB (localhost:5433), e.g.:
  DATABASE_URL=postgresql://...@localhost:5433/ingestion_test \
    ../.venv/Scripts/python.exe -m pytest tests/core/test_repo_lifecycle.py \
      -m integration
"""
import uuid

import pytest

import src.core.models  # noqa: F401  (register IngestionRequest for FK metadata)
from shared.models.document_node import DocumentNode
from src.core import db_utils
from src.core.database_session import get_engine, get_sessionmaker
from src.core.ingestion_ownership import (
    RepositoryBusy, reserve_ingestion, reserve_repo_mutation,
)
from src.core.status_manager import StatusManager
from src.core.codebase.codebase_persistence import CodebaseGraphPersistence

pytestmark = [pytest.mark.integration, pytest.mark.docker]


def _make_ingestion(session, repo_id=None, status="accepted"):
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
    with Session() as s:
        from src.core.models import IngestionRequest
        s.query(IngestionRequest).filter_by(repo_id=rid).delete(synchronize_session=False)
        s.commit()


class TestRepoIdPersistedIndependently:
    def test_repo_id_survives_graph_deletion(self, repo_id):
        """The exact gap issue #166 opens with: once repo_id lived only on
        document_nodes, a delete that finished graph cleanup but crashed
        before removing ingestion_requests could never be retried to
        completion, because list_ingestion_ids_for_repo had nothing left to
        enumerate. repo_id on ingestion_requests fixes that."""
        Session = get_sessionmaker()
        with Session() as s:
            ing = _make_ingestion(s, repo_id=repo_id, status="completed")
            _persist_one_node(s, repo_id, ing, "a")

        with Session() as s:
            CodebaseGraphPersistence(session=s).delete_repo_nodes(repo_id)

        # document_nodes is now empty for repo_id, but the ingestion_requests
        # row still carries repo_id -- a retried delete can still find it.
        ids = db_utils.list_ingestion_ids_for_repo(repo_id)
        assert ids == [str(ing)]

        db_utils.delete_ingestion_requests([str(ing)])

    def test_attempt_that_never_wrote_a_node_is_still_enumerable(self, repo_id):
        """An attempt that failed before graph_build wrote nothing to
        document_nodes at all; the old document_nodes-only lookup could
        never find it, leaking its ingestion_requests row forever."""
        Session = get_sessionmaker()
        with Session() as s:
            ing = _make_ingestion(s, repo_id=repo_id, status="accepted")
            StatusManager(s).mark_failed(ing, error="setup failed")

        ids = db_utils.list_ingestion_ids_for_repo(repo_id)
        assert ids == [str(ing)]
        db_utils.delete_ingestion_requests([str(ing)])


class TestGenerationResolution:
    def test_unknown_repo_has_no_generation(self, repo_id):
        assert db_utils.resolve_current_generation(repo_id) is None
        assert db_utils.generation_status(repo_id) == "unknown"

    def test_building_before_first_completion(self, repo_id):
        Session = get_sessionmaker()
        with Session() as s:
            _make_ingestion(s, repo_id=repo_id, status="running")

        assert db_utils.resolve_current_generation(repo_id) is None
        assert db_utils.generation_status(repo_id) == "building"

    def test_ready_after_completion_and_latest_wins(self, repo_id):
        """Mirrors the production invariant that mark_completed only ever
        follows a successful persist_graph: both generations here actually
        wrote nodes, and persist_graph's atomic replace leaves only the
        second generation's node as document_nodes' owner."""
        Session = get_sessionmaker()
        with Session() as s:
            ing1 = _make_ingestion(s, repo_id=repo_id, status="completed")
            _persist_one_node(s, repo_id, ing1, "first")
        with Session() as s:
            ing2 = _make_ingestion(s, repo_id=repo_id, status="completed")
            _persist_one_node(s, repo_id, ing2, "second")

        assert db_utils.generation_status(repo_id) == "ready"
        assert db_utils.resolve_current_generation(repo_id) == str(ing2)

    def test_full_graph_is_not_served_as_ready_while_its_owner_is_still_building(
        self, repo_id,
    ):
        """The defect this guards against: CodebaseGraphPersistence.persist_graph
        atomically replaces ALL of repo_id's document_nodes at *graph-build*
        time -- well before embedding finishes and mark_completed is
        written. So "document_nodes has rows for repo_id" does not mean
        "there is a stable, fully-ingested generation to serve": a rebuild's
        graph can already be in place while its embeddings (and therefore
        its retrievability) are still incomplete. A repo_id-only read would
        silently serve that half-finished generation as if it were normal.
        generation resolution must key off the owning ingestion's *status*,
        not merely whether document_nodes happens to be non-empty.
        """
        Session = get_sessionmaker()
        with Session() as s:
            ing1 = _make_ingestion(s, repo_id=repo_id, status="completed")
            _persist_one_node(s, repo_id, ing1, "old")

        graph = db_utils.get_full_graph_for_repo(repo_id)
        assert graph["generation_status"] == "ready"
        assert set(graph["nodes"].keys()) == {"pkg/old.py"}

        # A rebuild starts and its graph-build step runs (atomically
        # replacing ing1's nodes) before it reaches "completed".
        with Session() as s:
            ing2 = _make_ingestion(s, repo_id=repo_id, status="running")
            _persist_one_node(s, repo_id, ing2, "new")

        assert db_utils.generation_status(repo_id) == "building"
        graph_during_rebuild = db_utils.get_full_graph_for_repo(repo_id)
        assert graph_during_rebuild["generation_status"] == "building"
        assert graph_during_rebuild["nodes"] == {}, (
            "the in-flight rebuild's graph must not be served as ready even "
            "though it is now the only thing physically in document_nodes"
        )

        # Once it completes, its own graph becomes the servable generation.
        with Session() as s:
            StatusManager(s).mark_completed(ing2)
        graph_after_completion = db_utils.get_full_graph_for_repo(repo_id)
        assert graph_after_completion["generation_status"] == "ready"
        assert set(graph_after_completion["nodes"].keys()) == {"pkg/new.py"}

    def test_completed_survives_a_failed_attempt_with_no_graph_write(self, repo_id):
        """A rebuild attempt that fails before graph_build (e.g. clone
        failure) never calls persist_graph, so it never touches
        document_nodes. The prior completed generation's nodes are
        untouched and must keep being served as "ready" -- the failed
        attempt is invisible to generation_status precisely because it
        never became document_nodes' owner."""
        Session = get_sessionmaker()
        with Session() as s:
            ing1 = _make_ingestion(s, repo_id=repo_id, status="completed")
            _persist_one_node(s, repo_id, ing1, "old")
        with Session() as s:
            ing2 = _make_ingestion(s, repo_id=repo_id, status="running")
            StatusManager(s).mark_failed(ing2, error="clone failed")

        assert db_utils.generation_status(repo_id) == "ready"
        assert db_utils.resolve_current_generation(repo_id) == str(ing1)

    def test_failed_repo_with_no_graph_ever_written_is_reported_failed(self, repo_id):
        """No ingestion for this repo_id ever reached persist_graph, so
        document_nodes has no owner at all; the fallback must distinguish
        "tried and failed" from "never attempted" (unknown)."""
        Session = get_sessionmaker()
        with Session() as s:
            ing = _make_ingestion(s, repo_id=repo_id, status="running")
            StatusManager(s).mark_failed(ing, error="clone failed")

        assert db_utils.generation_status(repo_id) == "failed"
        assert db_utils.resolve_current_generation(repo_id) is None


class TestRepoScopeMutationLock:
    def test_delete_blocks_concurrent_ingest_and_vice_versa(self, repo_id):
        engine = get_engine()
        with reserve_repo_mutation(engine, repo_id):
            with pytest.raises(RepositoryBusy):
                reserve_ingestion(engine, uuid.uuid4(), repo_id=repo_id)

        ingestion_id = uuid.uuid4()
        with reserve_ingestion(engine, ingestion_id, repo_id=repo_id):
            with pytest.raises(RepositoryBusy):
                reserve_repo_mutation(engine, repo_id)

        # Released: both sides can now acquire it again.
        with reserve_repo_mutation(engine, repo_id):
            pass


class TestSupersededGenerationCleanup:
    def test_superseded_ids_excludes_current(self, repo_id):
        Session = get_sessionmaker()
        with Session() as s:
            ing1 = _make_ingestion(s, repo_id=repo_id, status="completed")
        with Session() as s:
            ing2 = _make_ingestion(s, repo_id=repo_id, status="completed")

        stale = db_utils.superseded_ingestion_ids_for_repo(repo_id, str(ing2))
        assert stale == [str(ing1)]

        db_utils.delete_ingestion_requests(stale)
        # ing2 remains the sole enumerable generation afterward.
        assert db_utils.list_ingestion_ids_for_repo(repo_id) == [str(ing2)]
