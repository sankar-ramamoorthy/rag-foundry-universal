# ingestion_service/tests/api/test_repo_generation_lineage.py
"""
Issue #196, Phase 4 (US2): GET /v1/repos/{repo_id}/generation exposes
snapshot lineage, per contracts/repo-generation-lineage.md.

T027: response shape (commit_sha, ingested_at, parent_generation_id,
is_incremental) matches the contract for a repo's first-ever generation.
T028: for a git-backed ingestion, commit_sha matches the fixture repo's
actual resolved HEAD SHA at clone time (not a placeholder).
T029: for a local_path ingestion, commit_sha is None (spec Non-Goals).

Exercises the real `_background_ingest_repo` orchestration end to end
against real Postgres and a real vector_store_service process, then
reads it back through the actual FastAPI route (not just db_utils
directly) -- proving the HTTP contract, not just the persistence.

Run with DATABASE_URL pointing at the test DB (localhost:5433), e.g.:
  DATABASE_URL=postgresql://...@localhost:5433/ingestion_test \
    ../.venv/Scripts/python.exe -m pytest \
    tests/api/test_repo_generation_lineage.py -m integration
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
from fastapi import FastAPI
from fastapi.testclient import TestClient

from src.api.v1 import codebase_ingest as api
from src.api.v1 import repos as repos_module
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


@pytest.fixture()
def client():
    app = FastAPI()
    app.include_router(repos_module.router)
    return TestClient(app)


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


def _counting_embedder():
    embedder = Mock()
    embedder.embed.side_effect = lambda chunks: [[0.0] * 1024 for _ in chunks]
    return embedder


def _run_ingestion(
    monkeypatch, vector_http_url, git_url, local_path, repo_id, ingestion_id,
):
    Session = get_sessionmaker()
    with Session() as s:
        StatusManager(s).create_request(
            ingestion_id=ingestion_id, source_type="repo", metadata={},
            repo_id=repo_id,
        )

    store = HttpVectorStore(vector_http_url)
    pipeline = IngestionPipeline(
        validator=Mock(), embedder=_counting_embedder(), vector_store=store,
    )
    monkeypatch.setattr(api, "_build_pipeline", lambda provider: pipeline)

    api._background_ingest_repo(ingestion_id, git_url, local_path, "mock", False)


def _init_git_fixture_repo(root: Path) -> str:
    """A real local git repo with one commit; returns its resolved HEAD SHA.

    Lazy import: GitPython is not installed in every environment that
    collects this module (e.g. CI's unit-tests job, which never runs
    this file's integration/docker-marked tests) -- matches the same
    lazy-import pattern _background_ingest_repo itself already uses.
    """
    import git  # GitPython
    (root / "a.py").write_text("def f():\n    return 1\n", encoding="utf-8")
    repo = git.Repo.init(root)
    repo.git.config("user.email", "test@example.com")
    repo.git.config("user.name", "Test")
    repo.index.add(["a.py"])
    repo.index.commit("initial")
    return repo.head.commit.hexsha


# ---------------------------------------------------------------------
# T027: response shape for a repo's first-ever generation
# ---------------------------------------------------------------------

def test_first_generation_lineage_shape(
    monkeypatch, vector_http_url, client, tmp_path,
):
    (tmp_path / "a.py").write_text("def f():\n    return 1\n", encoding="utf-8")
    repo_id = build_repo_id(str(tmp_path))
    try:
        ingestion_id = uuid.uuid4()
        _run_ingestion(
            monkeypatch, vector_http_url, None, str(tmp_path), repo_id, ingestion_id,
        )

        response = client.get(f"/repos/{repo_id}/generation")
        assert response.status_code == 200
        body = response.json()

        assert body["repo_id"] == repo_id
        assert body["ingestion_id"] == str(ingestion_id)
        assert body["generation_status"] == "ready"
        assert set(body) == {
            "repo_id", "ingestion_id", "generation_status",
            "commit_sha", "ingested_at", "parent_generation_id",
            "is_incremental",
        }
        # First-ever generation: local_path source, no parent, not incremental.
        assert body["commit_sha"] is None
        assert body["ingested_at"] is not None
        assert body["parent_generation_id"] is None
        assert body["is_incremental"] is False
    finally:
        _cleanup(repo_id)


# ---------------------------------------------------------------------
# T028: git-backed ingestion -- commit_sha is the real resolved HEAD SHA
# ---------------------------------------------------------------------

def test_git_backed_ingestion_reports_real_commit_sha(
    monkeypatch, vector_http_url, client, tmp_path,
):
    git_root = tmp_path / "fixture_repo"
    git_root.mkdir()
    expected_sha = _init_git_fixture_repo(git_root)
    repo_id = build_repo_id(str(git_root))
    try:
        ingestion_id = uuid.uuid4()
        _run_ingestion(
            monkeypatch, vector_http_url, str(git_root), None, repo_id, ingestion_id,
        )

        response = client.get(f"/repos/{repo_id}/generation")
        assert response.status_code == 200
        body = response.json()

        assert body["generation_status"] == "ready"
        assert body["commit_sha"] == expected_sha
        assert len(body["commit_sha"]) == 40  # a real SHA-1 hex digest
    finally:
        _cleanup(repo_id)


# ---------------------------------------------------------------------
# T029: local_path ingestion -- commit_sha stays None
# ---------------------------------------------------------------------

def test_local_path_ingestion_has_no_commit_sha(
    monkeypatch, vector_http_url, client, tmp_path,
):
    (tmp_path / "a.py").write_text("def f():\n    return 1\n", encoding="utf-8")
    repo_id = build_repo_id(str(tmp_path))
    try:
        ingestion_id = uuid.uuid4()
        _run_ingestion(
            monkeypatch, vector_http_url, None, str(tmp_path), repo_id, ingestion_id,
        )

        response = client.get(f"/repos/{repo_id}/generation")
        assert response.status_code == 200
        body = response.json()

        assert body["generation_status"] == "ready"
        assert body["commit_sha"] is None
    finally:
        _cleanup(repo_id)
