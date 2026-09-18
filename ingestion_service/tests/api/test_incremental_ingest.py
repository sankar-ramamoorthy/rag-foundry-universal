# ingestion_service/tests/api/test_incremental_ingest.py
"""
Issue #196, Phase 3 (US1): incremental re-ingestion end to end, through
the real `_background_ingest_repo` orchestration (not just the
persistence layer, which Phase 2's Foundational tests already cover)
against real Postgres and a real vector_store_service process.

T014: an unchanged file's document_id/vectors are reused, not
re-embedded, and re-tagged to the new generation.
T015: FR-006 -- a content-hash match with a different chunking_config_
version or embedding_config_version forces re-embedding anyway.
T016: FR-005 -- a non-`completed` prior generation performs a full
ingestion.
T017: FR-005a -- force_full_rebuild bypasses reuse even with a valid
prior generation, and still records parent_generation_id.

Run with DATABASE_URL pointing at the test DB (localhost:5433), e.g.:
  DATABASE_URL=postgresql://...@localhost:5433/ingestion_test \
    ../.venv/Scripts/python.exe -m pytest \
    tests/api/test_incremental_ingest.py -m integration
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
    """Real vector_store_service process, mirroring test_artifact_paging.py."""
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


@pytest.fixture()
def repo_id(tmp_path):
    # repo_id is a pure function of the source path (build_repo_id),
    # recomputed internally by _background_ingest_repo -- it must match
    # exactly, so it is derived here rather than an arbitrary UUID.
    rid = build_repo_id(str(tmp_path))
    yield rid
    Session = get_sessionmaker()
    with Session() as s:
        s.query(DocumentNode).filter_by(repo_id=rid).delete(synchronize_session=False)
        s.commit()
    with Session() as s:
        s.query(IngestionRequest).filter_by(repo_id=rid).delete(
            synchronize_session=False
        )
        s.commit()


def _write_repo(root: Path, touch_body: str):
    (root / "keep.py").write_text(
        "def keep():\n    return 1\n", encoding="utf-8",
    )
    (root / "touch.py").write_text(touch_body, encoding="utf-8")


def _counting_embedder():
    embedded_canonical_ids: set[str] = set()

    def _embed(chunks):
        for chunk in chunks:
            cid = chunk.metadata.get("canonical_id")
            if cid:
                embedded_canonical_ids.add(cid)
        return [[0.0] * 1024 for _ in chunks]

    embedder = Mock()
    embedder.embed.side_effect = _embed
    return embedder, embedded_canonical_ids


def _run_ingestion(
    monkeypatch, vector_http_url, repo_path, repo_id, ingestion_id,
    *, force_full_rebuild=False, embedder=None,
):
    Session = get_sessionmaker()
    with Session() as s:
        StatusManager(s).create_request(
            ingestion_id=ingestion_id, source_type="repo", metadata={},
            repo_id=repo_id,
        )

    if embedder is None:
        embedder, _ = _counting_embedder()

    store = HttpVectorStore(vector_http_url)
    pipeline = IngestionPipeline(
        validator=Mock(), embedder=embedder, vector_store=store,
    )
    monkeypatch.setattr(api, "_build_pipeline", lambda provider: pipeline)

    api._background_ingest_repo(
        ingestion_id, None, str(repo_path), "mock", force_full_rebuild,
    )


def _request_row(ingestion_id):
    Session = get_sessionmaker()
    with Session() as s:
        return s.get(IngestionRequest, ingestion_id)


def _document_id(repo_id, canonical_id):
    Session = get_sessionmaker()
    with Session() as s:
        row = (
            s.query(DocumentNode)
            .filter_by(repo_id=repo_id, canonical_id=canonical_id)
            .one()
        )
        return row.document_id


def _vector_ingestion_ids(document_id):
    Session = get_sessionmaker()
    with Session() as s:
        rows = s.execute(
            text(
                "SELECT ingestion_id FROM ingestion_service.vector_chunks "
                "WHERE document_id = :document_id"
            ),
            {"document_id": document_id},
        ).all()
        return {str(r[0]) for r in rows}


# ---------------------------------------------------------------------
# T014: unchanged file reuses document_id + vectors, no re-embed, re-tagged
# ---------------------------------------------------------------------

def test_unchanged_file_reuses_vectors_and_retags(
    monkeypatch, vector_http_url, repo_id, tmp_path,
):
    _write_repo(tmp_path, "def touch():\n    return 1\n")

    id1 = uuid.uuid4()
    _run_ingestion(monkeypatch, vector_http_url, tmp_path, repo_id, id1)
    req1 = _request_row(id1)
    assert req1.status == "completed"
    assert req1.is_incremental is False  # no prior generation

    keep_doc_id = _document_id(repo_id, "keep.py")
    assert _vector_ingestion_ids(keep_doc_id) == {str(id1)}

    # Edit touch.py only; keep.py's bytes are untouched.
    (tmp_path / "touch.py").write_text("def touch():\n    return 2\n", encoding="utf-8")

    id2 = uuid.uuid4()
    embedder, embedded_ids = _counting_embedder()
    _run_ingestion(
        monkeypatch, vector_http_url, tmp_path, repo_id, id2, embedder=embedder,
    )
    req2 = _request_row(id2)
    assert req2.status == "completed"
    assert req2.is_incremental is True
    assert str(req2.parent_generation_id) == str(id1)

    assert "keep.py" not in embedded_ids and "keep.py#keep" not in embedded_ids, (
        "an unchanged file must not be re-embedded"
    )
    assert "touch.py" in embedded_ids or "touch.py#touch" in embedded_ids, (
        "the changed file must be re-embedded"
    )

    # document_id stability (R1) + FR-007b: same document_id, vectors
    # re-tagged to the new generation, not deleted and re-created.
    assert _document_id(repo_id, "keep.py") == keep_doc_id
    assert _vector_ingestion_ids(keep_doc_id) == {str(id2)}


# ---------------------------------------------------------------------
# T015: FR-006 -- a chunking/embedding config change forces full re-embed
# ---------------------------------------------------------------------

def test_config_version_mismatch_forces_full_reembed(
    monkeypatch, vector_http_url, repo_id, tmp_path,
):
    _write_repo(tmp_path, "def touch():\n    return 1\n")

    id1 = uuid.uuid4()
    _run_ingestion(monkeypatch, vector_http_url, tmp_path, repo_id, id1)

    # Nothing about the files changes -- only the chunking config "version".
    monkeypatch.setattr(api.ChunkerFactory, "VERSION", "heuristic-v2-test")

    id2 = uuid.uuid4()
    embedder, embedded_ids = _counting_embedder()
    _run_ingestion(
        monkeypatch, vector_http_url, tmp_path, repo_id, id2, embedder=embedder,
    )
    req2 = _request_row(id2)
    assert req2.is_incremental is True  # a valid prior generation still exists

    assert "keep.py" in embedded_ids, (
        "a chunking_config_version mismatch must force re-embedding for "
        "EVERY file, including ones whose content didn't change"
    )
    assert "touch.py" in embedded_ids


# ---------------------------------------------------------------------
# T016: FR-005 -- prior generation not completed -> full ingestion
# ---------------------------------------------------------------------

def test_non_completed_prior_generation_performs_full_ingestion(
    monkeypatch, vector_http_url, repo_id, tmp_path,
):
    _write_repo(tmp_path, "def touch():\n    return 1\n")

    # A prior attempt that never completed (still "running").
    stuck_id = uuid.uuid4()
    Session = get_sessionmaker()
    with Session() as s:
        StatusManager(s).create_request(
            ingestion_id=stuck_id, source_type="repo", metadata={}, repo_id=repo_id,
        )
        StatusManager(s).mark_running(stuck_id)

    id2 = uuid.uuid4()
    embedder, embedded_ids = _counting_embedder()
    _run_ingestion(
        monkeypatch, vector_http_url, tmp_path, repo_id, id2, embedder=embedder,
    )
    req2 = _request_row(id2)
    assert req2.is_incremental is False
    assert "keep.py" in embedded_ids
    assert "touch.py" in embedded_ids


# ---------------------------------------------------------------------
# T017: FR-005a -- force_full_rebuild bypasses reuse, still records lineage
# ---------------------------------------------------------------------

def test_force_full_rebuild_bypasses_reuse_but_records_parent(
    monkeypatch, vector_http_url, repo_id, tmp_path,
):
    _write_repo(tmp_path, "def touch():\n    return 1\n")

    id1 = uuid.uuid4()
    _run_ingestion(monkeypatch, vector_http_url, tmp_path, repo_id, id1)

    id2 = uuid.uuid4()
    embedder, embedded_ids = _counting_embedder()
    _run_ingestion(
        monkeypatch, vector_http_url, tmp_path, repo_id, id2,
        embedder=embedder, force_full_rebuild=True,
    )
    req2 = _request_row(id2)

    assert req2.is_incremental is False, (
        "force_full_rebuild must bypass reuse classification entirely"
    )
    assert str(req2.parent_generation_id) == str(id1), (
        "parent_generation_id records lineage regardless of "
        "force_full_rebuild -- it is not a reuse opt-out"
    )
    assert "keep.py" in embedded_ids, (
        "force_full_rebuild must re-embed every file, even unchanged ones"
    )
