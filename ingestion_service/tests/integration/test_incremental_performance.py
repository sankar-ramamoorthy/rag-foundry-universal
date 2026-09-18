# ingestion_service/tests/integration/test_incremental_performance.py
"""
Issue #196, T018 (SC-001): a ~2,000-file fixture repo with 1 file edited
re-embeds only that file's artifacts and completes in under 30 seconds.

Opt-in (marked slow) given fixture size -- not part of routine
`-m "integration or docker"` sweeps. Run explicitly, e.g.:
  DATABASE_URL=postgresql://...@localhost:5433/ingestion_test \
    ../.venv/Scripts/python.exe -m pytest \
    tests/integration/test_incremental_performance.py -m slow
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

from src.api.v1 import codebase_ingest as api
from src.core.database_session import get_sessionmaker, get_engine
from src.core.status_manager import StatusManager
from src.core.models import IngestionRequest
from shared.models.document_node import DocumentNode
from src.core.pipeline import IngestionPipeline
from src.core.http_vectorstore import HttpVectorStore
from src.core.codebase.identity import build_repo_id

pytestmark = [pytest.mark.integration, pytest.mark.docker, pytest.mark.slow]

FIXTURE_FILE_COUNT = 2000


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


def _generate_fixture_repo(root: Path, count: int) -> None:
    for i in range(count):
        (root / f"mod_{i}.py").write_text(
            f"def f_{i}():\n    return {i}\n", encoding="utf-8",
        )


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
    monkeypatch, vector_http_url, repo_path, repo_id, ingestion_id, embedder,
):
    Session = get_sessionmaker()
    with Session() as s:
        StatusManager(s).create_request(
            ingestion_id=ingestion_id, source_type="repo", metadata={},
            repo_id=repo_id,
        )

    store = HttpVectorStore(vector_http_url)
    pipeline = IngestionPipeline(
        validator=Mock(), embedder=embedder, vector_store=store,
    )
    monkeypatch.setattr(api, "_build_pipeline", lambda provider: pipeline)

    api._background_ingest_repo(ingestion_id, None, str(repo_path), "mock", False)


def test_incremental_reingest_of_large_repo_completes_within_bound(
    monkeypatch, vector_http_url, tmp_path,
):
    _generate_fixture_repo(tmp_path, FIXTURE_FILE_COUNT)
    repo_id = build_repo_id(str(tmp_path))

    try:
        id1 = uuid.uuid4()
        embedder1, _ = _counting_embedder()
        _run_ingestion(monkeypatch, vector_http_url, tmp_path, repo_id, id1, embedder1)

        Session = get_sessionmaker()
        with Session() as s:
            req1 = s.get(IngestionRequest, id1)
            assert req1.status == "completed"

        # Edit exactly one file.
        (tmp_path / "mod_0.py").write_text(
            "def f_0():\n    return -1\n", encoding="utf-8",
        )

        id2 = uuid.uuid4()
        embedder2, embedded_ids = _counting_embedder()
        start = time.monotonic()
        _run_ingestion(monkeypatch, vector_http_url, tmp_path, repo_id, id2, embedder2)
        elapsed = time.monotonic() - start

        with Session() as s:
            req2 = s.get(IngestionRequest, id2)
            assert req2.status == "completed"
            assert req2.is_incremental is True

        assert embedded_ids == {"mod_0.py", "mod_0.py#f_0"}, (
            f"expected only mod_0.py's artifacts re-embedded, got {embedded_ids}"
        )
        assert elapsed < 30, (
            f"incremental re-ingest of a {FIXTURE_FILE_COUNT}-file repo with "
            f"1 file changed took {elapsed:.1f}s, expected < 30s (SC-001)"
        )
    finally:
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
