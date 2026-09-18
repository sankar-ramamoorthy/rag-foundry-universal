# ingestion_service/tests/integration/test_incremental_equivalence.py
"""
Issue #196, Phase 6 (T036): the FR-012/SC-002 equivalence guarantee --
incremental ingestion's end state must match a clean full rebuild's end
state, for the same target commit. This is the acceptance bar ADR-036
already sets, applied here specifically (see quickstart.md step 4).

Scripts a deterministic add/change/delete edit against a small fixture
repo, then ingests the *target* state two different ways:

- Generation A (baseline): one full ingestion straight of the target
  state, into a fresh repo_id.
- Generation B (incremental): a full ingestion of the *prior* state
  into a different fresh repo_id, then the scripted edits applied on
  disk, then a second, incremental ingestion of the target state.

Asserts A and B converge to the same graph (ignoring document_id/
ingestion_id/repo_id, which are expected to differ) and the same
vector chunk content.

commit_sha is intentionally not asserted for byte-for-byte git SHA
equality here: both generations use `local_path` (matching every other
Phase 3/5 test in this suite), for which commit_sha is `None` per spec
Non-Goals -- so the "matching commit_sha lineage" claim reduces to
None == None. Git-backed commit_sha *correctness* (the real resolved
HEAD SHA, not a placeholder) is already independently covered by T028
(test_repo_generation_lineage.py) -- forcing two independently-created
git repos to hash-collide on a real commit SHA would add real fragility
here for no additional coverage.

Run with DATABASE_URL pointing at the test DB (localhost:5433), e.g.:
  DATABASE_URL=postgresql://...@localhost:5433/ingestion_test \
    ../.venv/Scripts/python.exe -m pytest \
    tests/integration/test_incremental_equivalence.py -m integration
"""
import os
import socket
import subprocess
import sys
import time
import uuid
from pathlib import Path
from unittest.mock import Mock

import pytest
import requests
from sqlalchemy import text

from src.api.v1 import codebase_ingest as api
from src.core.database_session import get_sessionmaker, get_engine
from src.core.status_manager import StatusManager
from src.core.models import IngestionRequest
from shared.models.document_node import DocumentNode
from src.core.pipeline import IngestionPipeline
from src.core.http_vectorstore import HttpVectorStore
from src.core.codebase.identity import build_repo_id

pytestmark = [pytest.mark.integration, pytest.mark.docker]


@pytest.fixture(scope="module")
def vector_http_url():
    engine = get_engine()
    assert engine.url.database and engine.url.database.endswith("_test"), (
        "HTTP durability tests require an isolated *_test database"
    )
    root = Path(__file__).resolve().parents[3]
    with socket.socket() as reserved:
        reserved.bind(("127.0.0.1", 0))
        port = reserved.getsockname()[1]
    env = {
        **os.environ,
        "DATABASE_URL": engine.url.render_as_string(hide_password=False),
        "PYTHONPATH": os.pathsep.join([str(root), str(root / "vector_store_service")]),
        "EMBEDDING_PROVIDER": "mock",
        "VECTOR_DIMENSION": "1024",
        "PYTHON_DOTENV_DISABLED": "1",
    }
    process = subprocess.Popen(
        [
            sys.executable, "-m", "uvicorn", "src.api.v1.main:app",
            "--host", "127.0.0.1", "--port", str(port),
        ],
        cwd=root / "vector_store_service",
        env=env, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
    )
    url = f"http://127.0.0.1:{port}"
    try:
        deadline = time.monotonic() + 20
        while time.monotonic() < deadline:
            assert process.poll() is None, (
                "Isolated vector service exited during startup"
            )
            try:
                if requests.get(url + "/health", timeout=0.5).status_code == 200:
                    break
            except requests.RequestException:
                pass
            time.sleep(0.1)
        else:
            pytest.fail("Isolated vector HTTP service failed to become healthy")
        yield url
    finally:
        process.terminate()
        try:
            process.wait(timeout=5)
        except subprocess.TimeoutExpired:
            process.kill()
            process.wait(timeout=5)


def _write_prior_state(root: Path) -> None:
    (root / "pkg").mkdir(parents=True, exist_ok=True)
    (root / "pkg" / "a.py").write_text(
        "def helper():\n    return 1\n", encoding="utf-8",
    )
    (root / "pkg" / "b.py").write_text(
        "def use():\n    return helper()\n", encoding="utf-8",
    )
    (root / "pkg" / "c.py").write_text(
        "def stable():\n    return 42\n", encoding="utf-8",
    )


def _write_target_state(root: Path) -> None:
    """Prior state with a delete (a.py), a change (c.py), and an add (d.py)."""
    (root / "pkg").mkdir(parents=True, exist_ok=True)
    a_py = root / "pkg" / "a.py"
    if a_py.exists():
        a_py.unlink()
    (root / "pkg" / "b.py").write_text(
        "def use():\n    return helper()\n", encoding="utf-8",
    )
    (root / "pkg" / "c.py").write_text(
        "def stable():\n    return 43\n", encoding="utf-8",
    )
    (root / "pkg" / "d.py").write_text(
        "def new_fn():\n    return use()\n", encoding="utf-8",
    )


def _apply_target_edits(root: Path) -> None:
    """Mutate a checkout already at prior state, in place, to target state."""
    (root / "pkg" / "a.py").unlink()
    (root / "pkg" / "c.py").write_text(
        "def stable():\n    return 43\n", encoding="utf-8",
    )
    (root / "pkg" / "d.py").write_text(
        "def new_fn():\n    return use()\n", encoding="utf-8",
    )


def _deterministic_embedder():
    """chunk_text is what's compared, not the vector -- a fixed-shape
    embedding is enough; no need for content-derived values."""
    embedder = Mock()
    embedder.embed.side_effect = lambda chunks: [[0.0] * 1024 for _ in chunks]
    return embedder


def _run_ingestion(
    monkeypatch, vector_http_url, repo_path, repo_id, ingestion_id,
    *, force_full_rebuild=False,
):
    Session = get_sessionmaker()
    with Session() as s:
        StatusManager(s).create_request(
            ingestion_id=ingestion_id, source_type="repo", metadata={},
            repo_id=repo_id,
        )

    store = HttpVectorStore(vector_http_url)
    pipeline = IngestionPipeline(
        validator=Mock(), embedder=_deterministic_embedder(), vector_store=store,
    )
    monkeypatch.setattr(api, "_build_pipeline", lambda provider: pipeline)

    # The post-completion superseded-generation cleanup (codebase_ingest.py,
    # #166) builds its OWN HttpVectorStore from settings.VECTOR_STORE_
    # SERVICE_URL rather than reusing the pipeline's vector_store -- correct
    # under docker-compose (that hostname resolves there), but pointed at
    # nothing in this isolated-process test, silently no-op'ing (best-
    # effort/non-fatal) and leaving a changed file's prior-generation
    # vectors behind. Point it at the same isolated test service so the
    # equivalence assertions below are checking real cleanup, not masking
    # a no-op.
    monkeypatch.setattr(
        api.get_settings(), "VECTOR_STORE_SERVICE_URL", vector_http_url,
    )

    api._background_ingest_repo(
        ingestion_id, None, str(repo_path), "mock", force_full_rebuild,
    )


def _cleanup(repo_id):
    Session = get_sessionmaker()
    with Session() as s:
        s.query(DocumentNode).filter_by(repo_id=repo_id).delete(
            synchronize_session=False
        )
        s.commit()
    with Session() as s:
        s.query(IngestionRequest).filter_by(repo_id=repo_id).delete(
            synchronize_session=False
        )
        s.commit()


def _edge_set(repo_id):
    """{(from_canonical_id, relation_type, to_canonical_id)} -- identity
    only, ignoring document_id/ingestion_id/repo_id."""
    Session = get_sessionmaker()
    with Session() as s:
        rows = s.execute(
            text(
                "SELECT fn.canonical_id, r.relation_type, tn.canonical_id "
                "FROM ingestion_service.document_relationships r "
                "JOIN ingestion_service.document_nodes fn "
                "  ON fn.document_id = r.from_document_id "
                "JOIN ingestion_service.document_nodes tn "
                "  ON tn.document_id = r.to_document_id "
                "WHERE r.repo_id = :repo_id"
            ),
            {"repo_id": repo_id},
        ).all()
        return {tuple(row) for row in rows}


def _vector_tuple_set(repo_id):
    """{(canonical_id, chunk_index, chunk_text)} -- identity only."""
    Session = get_sessionmaker()
    with Session() as s:
        rows = s.execute(
            text(
                "SELECT n.canonical_id, v.chunk_index, v.chunk_text "
                "FROM ingestion_service.vector_chunks v "
                "JOIN ingestion_service.document_nodes n "
                "  ON n.document_id = v.document_id "
                "WHERE n.repo_id = :repo_id"
            ),
            {"repo_id": repo_id},
        ).all()
        return {tuple(row) for row in rows}


def _canonical_id_set(repo_id):
    Session = get_sessionmaker()
    with Session() as s:
        rows = (
            s.query(DocumentNode.canonical_id)
            .filter(DocumentNode.repo_id == repo_id)
            .all()
        )
        return {r[0] for r in rows}


def test_incremental_end_state_matches_full_rebuild(
    monkeypatch, vector_http_url, tmp_path,
):
    baseline_root = tmp_path / "baseline"
    incremental_root = tmp_path / "incremental"
    baseline_root.mkdir()
    incremental_root.mkdir()

    repo_id_a = build_repo_id(str(baseline_root))
    repo_id_b = build_repo_id(str(incremental_root))
    assert repo_id_a != repo_id_b, (
        "distinct source paths must produce distinct repo_ids -- required "
        "so A and B never share rows in the same table"
    )

    try:
        # --- Generation A (baseline): one full ingest of the TARGET state.
        _write_target_state(baseline_root)
        id_a = uuid.uuid4()
        _run_ingestion(monkeypatch, vector_http_url, baseline_root, repo_id_a, id_a)
        assert _request_status(id_a) == "completed"

        # --- Generation B (incremental): full ingest of PRIOR state, then
        # scripted add/change/delete edits, then an incremental re-ingest.
        _write_prior_state(incremental_root)
        id_b1 = uuid.uuid4()
        _run_ingestion(monkeypatch, vector_http_url, incremental_root, repo_id_b, id_b1)
        assert _request_status(id_b1) == "completed"
        assert _request_is_incremental(id_b1) is False  # no prior generation yet

        _apply_target_edits(incremental_root)
        id_b2 = uuid.uuid4()
        _run_ingestion(monkeypatch, vector_http_url, incremental_root, repo_id_b, id_b2)
        assert _request_status(id_b2) == "completed"
        assert _request_is_incremental(id_b2) is True, (
            "sanity: this must actually exercise the incremental path, "
            "not silently fall back to full"
        )

        # --- Equivalence assertions.
        canonical_a = _canonical_id_set(repo_id_a)
        canonical_b = _canonical_id_set(repo_id_b)
        assert canonical_a == canonical_b, (
            f"node identity sets diverged: only in A={canonical_a - canonical_b}, "
            f"only in B={canonical_b - canonical_a}"
        )
        assert "pkg/a.py" not in canonical_b, "deleted file must not survive"
        assert "pkg/d.py" in canonical_b, "added file must be present"

        edges_a = _edge_set(repo_id_a)
        edges_b = _edge_set(repo_id_b)
        assert edges_a == edges_b, (
            f"edge sets diverged: only in A={edges_a - edges_b}, "
            f"only in B={edges_b - edges_a}"
        )

        vectors_a = _vector_tuple_set(repo_id_a)
        vectors_b = _vector_tuple_set(repo_id_b)
        assert vectors_a == vectors_b, (
            f"vector chunk tuples diverged: only in A={vectors_a - vectors_b}, "
            f"only in B={vectors_b - vectors_a}"
        )

        # commit_sha lineage: both local_path -- None == None (see module docstring).
        assert _request_commit_sha(id_a) is None
        assert _request_commit_sha(id_b2) is None
    finally:
        _cleanup(repo_id_a)
        _cleanup(repo_id_b)


def _request_status(ingestion_id):
    Session = get_sessionmaker()
    with Session() as s:
        return s.get(IngestionRequest, ingestion_id).status


def _request_is_incremental(ingestion_id):
    Session = get_sessionmaker()
    with Session() as s:
        return s.get(IngestionRequest, ingestion_id).is_incremental


def _request_commit_sha(ingestion_id):
    Session = get_sessionmaker()
    with Session() as s:
        return s.get(IngestionRequest, ingestion_id).commit_sha
