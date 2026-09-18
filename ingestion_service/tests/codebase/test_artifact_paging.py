"""#160 real PostgreSQL page isolation, input envelope and generation checks."""

import uuid
import os
from pathlib import Path
import socket
import subprocess
import sys
import time
import json
from contextlib import contextmanager

import pytest
from sqlalchemy import event, text
import requests

from shared.models.document_node import DocumentNode
from src.core.models import IngestionRequest
from src.core.database_session import get_sessionmaker, get_engine
from src.core.status_manager import StatusManager
from src.core.codebase.codebase_persistence import CodebaseGraphPersistence


pytestmark = [pytest.mark.integration, pytest.mark.docker]


@pytest.fixture(scope="module")
def vector_http_url():
    """Real service in a separate interpreter avoids ingestion's `src` imports."""
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
            sys.executable,
            "-m",
            "uvicorn",
            "src.api.v1.main:app",
            "--host",
            "127.0.0.1",
            "--port",
            str(port),
        ],
        cwd=root / "vector_store_service",
        env=env,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
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


@pytest.fixture
def corpus():
    with _corpus() as value:
        yield value


@contextmanager
def _corpus(repo=None):
    repo, attempt = repo or str(uuid.uuid4()), uuid.uuid4()
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
    try:
        yield repo, str(attempt), factory
    finally:
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
                    str(uuid.uuid4()),
                    attempt,
                    page_size=2,
                    max_artifact_bytes=20,
                    expected_nodes=0,
                )
            )
            == []
        )


@pytest.mark.parametrize("terminal", ["completed", "failed"])
def test_progress_and_terminal_stage_visible_in_fresh_session(corpus, terminal):
    _, attempt, factory = corpus
    identifier = uuid.UUID(attempt)
    with factory() as session:
        manager = StatusManager(session)
        manager.mark_running(identifier)
        manager.update_embed_progress(
            identifier,
            {
                "stage": "embedding",
                "nodes_processed": 1,
                "nodes_total": 2,
                "chunks_persisted": 7,
                "max_buffer_chunks": 7,
                "max_buffer_bytes": 7000,
            },
        )
        with factory() as observer:
            row = (
                observer.query(IngestionRequest)
                .filter_by(ingestion_id=identifier)
                .one()
            )
            assert row.status == "running"
            assert row.ingestion_metadata["embed_progress"]["chunks_persisted"] == 7
        if terminal == "failed":
            manager.mark_failed(identifier, error="fixture interruption")
        else:
            manager.mark_completed(identifier)
    with factory() as observer:
        row = observer.query(IngestionRequest).filter_by(ingestion_id=identifier).one()
        assert row.status == terminal and row.finished_at is not None
        assert row.ingestion_metadata["embed_progress"]["stage"] == terminal
        assert row.ingestion_metadata["embed_progress"]["chunks_persisted"] == 7
        if terminal == "failed":
            assert row.ingestion_metadata["error"] == "fixture interruption"


def test_progress_status_contract_with_real_paging(corpus, monkeypatch):
    from unittest.mock import Mock
    from src.api.v1 import codebase_ingest as api
    from src.core.config import Settings
    from src.core.http_vectorstore import HttpVectorStore
    from src.core.pipeline import IngestionPipeline

    repo, attempt, factory = corpus
    identifier = uuid.UUID(attempt)
    monkeypatch.setattr(api, "SessionLocal", factory)
    store = HttpVectorStore("http://unused")
    store.add_vectors = Mock()
    store.delete_by_ingestion_id = Mock()
    embedder = Mock()
    embedder.embed.side_effect = lambda chunks: [[0.0]] * len(chunks)
    pipeline = IngestionPipeline(
        validator=Mock(), embedder=embedder, vector_store=store
    )
    with factory() as session:
        manager = StatusManager(session)
        manager.mark_running(identifier)

        def report(progress):
            manager.update_embed_progress(identifier, progress)
            response = api.get_repo_ingest_status(attempt)
            assert response.embed_progress == progress
            assert response.status == "running"

        count, skipped = api._embed_repo_artifacts(
            pipeline,
            CodebaseGraphPersistence(session),
            repo,
            attempt,
            5,
            "mock",
            Settings(
                _env_file=None,
                DATABASE_URL="unused",
                INGESTION_NODE_PAGE_SIZE=1,
                INGESTION_EMBED_BATCH_SIZE=1,
            ),
            report,
        )
        assert count == 2 and skipped == 0
        manager.mark_completed(identifier)
    response = api.get_repo_ingest_status(attempt)
    assert response.status == "completed"
    assert response.embed_progress["nodes_processed"] == 2
    assert response.embed_progress["stage"] == "completed"


def _stored_vectors(factory, attempt):
    with factory() as session:
        return session.execute(
            text("""
            SELECT n.canonical_id, vc.chunk_index, vc.chunk_text,
                   vc.source_metadata, vc.vector::text, vc.provider
            FROM ingestion_service.vector_chunks vc
            JOIN ingestion_service.document_nodes n ON n.document_id = vc.document_id
            WHERE vc.ingestion_id = :attempt
            ORDER BY n.canonical_id, vc.chunk_index
        """),
            {"attempt": attempt},
        ).all()


def _real_embedding_fixture(corpus, vector_http_url, *, buffer_size, fail_after=None):
    from unittest.mock import Mock
    from src.api.v1 import codebase_ingest as api
    from src.core.config import Settings
    from src.core.http_vectorstore import HttpVectorStore
    from src.core.pipeline import IngestionPipeline

    repo, attempt, factory = corpus
    with factory() as session:
        session.query(DocumentNode).filter_by(repo_id=repo, canonical_id="4.py").update(
            {DocumentNode.text: "x" * 128000}
        )
        session.commit()
    store = HttpVectorStore(vector_http_url)
    store.delete_by_ingestion_id(attempt)
    calls = 0
    actual_write = store.add_vectors

    def write(records):
        nonlocal calls
        if fail_after is not None and calls >= fail_after:
            raise RuntimeError("injected failure after committed HTTP batches")
        actual_write(records)
        calls += 1
        # A fresh DB session must see each HTTP acknowledgement immediately.
        assert len(_stored_vectors(factory, attempt)) == calls * buffer_size or (
            len(records) < buffer_size
        )

    store.add_vectors = write
    embedder = Mock()
    embedder.embed.side_effect = lambda chunks: [
        [float(len(chunk.content))] + [0.0] * 1023 for chunk in chunks
    ]
    pipeline = IngestionPipeline(
        validator=Mock(), embedder=embedder, vector_store=store
    )
    with factory() as session:
        manager = StatusManager(session)
        manager.mark_running(uuid.UUID(attempt))
        try:
            api._embed_repo_artifacts(
                pipeline,
                CodebaseGraphPersistence(session),
                repo,
                attempt,
                5,
                "mock",
                Settings(
                    _env_file=None,
                    DATABASE_URL="unused",
                    INGESTION_NODE_PAGE_SIZE=1,
                    INGESTION_EMBED_BATCH_SIZE=buffer_size,
                ),
                lambda progress: manager.update_embed_progress(
                    uuid.UUID(attempt), progress
                ),
            )
        except RuntimeError as exc:
            manager.mark_failed(uuid.UUID(attempt), error=str(exc))
            raise
        manager.mark_completed(uuid.UUID(attempt))
    return _stored_vectors(factory, attempt)


def test_real_http_vector_writes_have_normalized_buffer_parity(vector_http_url):
    # Each run is a fresh attempt, not resurrection of a completed job (#161).
    repo = str(uuid.uuid4())
    outputs = []
    for size in (1, 7, 128):
        with _corpus(repo) as fixture:
            outputs.append(_real_embedding_fixture(
                fixture, vector_http_url, buffer_size=size,
            ))
    assert len(outputs[0]) == 144  # one short artifact + actual 143-chunk artifact
    assert outputs[0] == outputs[1] == outputs[2]
    indices = [row.chunk_index for row in outputs[0] if row.canonical_id == "4.py"]
    assert indices == list(range(143))


def test_acknowledged_http_batches_survive_later_failure(corpus, vector_http_url):
    _, attempt, factory = corpus
    with pytest.raises(RuntimeError, match="injected failure"):
        _real_embedding_fixture(corpus, vector_http_url, buffer_size=7, fail_after=2)
    rows = _stored_vectors(factory, attempt)
    assert len(rows) == 14
    with factory() as observer:
        request = (
            observer.query(IngestionRequest)
            .filter_by(
                ingestion_id=uuid.UUID(attempt),
            )
            .one()
        )
        assert request.status == "failed"
        progress = request.ingestion_metadata["embed_progress"]
        assert progress["chunks_persisted"] == 14 and progress["stage"] == "failed"


def test_hard_kill_after_vector_ack_retains_data_and_recovers(corpus, vector_http_url):
    """#161: a real process dies after 14 acknowledged HTTP vector writes."""
    import queue
    import threading
    from src.core.ingestion_ownership import reconcile_ingestions
    from src.core.http_vectorstore import HttpVectorStore

    _, attempt, factory = corpus
    with factory() as session:
        document = session.query(DocumentNode).filter_by(ingestion_id=attempt).first()
        document_id = str(document.document_id)
    program = """
import sys, time
from uuid import UUID, uuid4
from src.core.database_session import get_engine, get_sessionmaker
from src.core.ingestion_ownership import AdvisoryGuard, owned_metadata
from src.core.models import IngestionRequest
from src.core.status_manager import StatusManager
from src.core.http_vectorstore import HttpVectorStore
from src.core.worker_context import ownership_check
attempt, document, url = sys.argv[1:]
guard = AdvisoryGuard(get_engine())
assert guard.try_lock('admission', 'global-single-job')
assert guard.try_lock('attempt', attempt)
ownership_check.set(guard.check)
with get_sessionmaker()() as session:
    request = session.get(IngestionRequest, UUID(attempt))
    request.ingestion_metadata = owned_metadata(request.ingestion_metadata or {})
    session.commit()
    status = StatusManager(session)
    status.mark_running(UUID(attempt))
    store = HttpVectorStore(url)
    for batch in range(2):
        records = [{
            'vector': [1.0] + [0.0] * 1023,
            'metadata': {
                'ingestion_id': attempt, 'document_id': document,
                'chunk_id': str(uuid4()), 'chunk_index': batch * 7 + i,
                'chunk_text': 'durable fixture', 'provider': 'mock',
                'chunk_strategy': 'fixture', 'source_metadata': {},
            },
        } for i in range(7)]
        store.add_vectors(records)
        status.update_embed_progress(UUID(attempt), {
            'stage': 'embedding', 'chunks_persisted': (batch + 1) * 7,
        })
print('ready', flush=True)
time.sleep(60)
"""
    root = Path(__file__).resolve().parents[3]
    child = subprocess.Popen(
        [sys.executable, "-c", program, attempt, document_id, vector_http_url],
        stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True,
        env={**os.environ, "PYTHONPATH": os.pathsep.join([
            str(root), str(root / "ingestion_service"),
        ])},
    )
    try:
        ready = queue.Queue()
        threading.Thread(
            target=lambda: ready.put(child.stdout.readline()), daemon=True,
        ).start()
        assert ready.get(timeout=20).strip() == "ready"
        assert len(_stored_vectors(factory, attempt)) == 14
        assert reconcile_ingestions(get_engine()) == 0
        child.kill()
        child.communicate(timeout=10)
        assert reconcile_ingestions(get_engine()) == 1
        assert len(_stored_vectors(factory, attempt)) == 14
        with factory() as session:
            request = session.get(IngestionRequest, uuid.UUID(attempt))
            assert request.status == "failed" and request.finished_at is not None
            assert request.ingestion_metadata["embed_progress"] == {
                "stage": "failed", "chunks_persisted": 14,
            }
    finally:
        if child.poll() is None:
            child.kill()
        child.communicate(timeout=10)
        HttpVectorStore(vector_http_url).delete_by_ingestion_id(attempt)


def test_capture_real_paging_plan(corpus):
    """Record actual planner behavior before proposing a new paging index."""
    repo, attempt, factory = corpus
    with factory() as session:
        nodes = [
            {
                "canonical_id": f"p{i}.py",
                "relative_path": f"p{i}.py",
                "text": "def f(): return 1",
                "ingestion_id": attempt,
            }
            for i in range(4000)
        ]
        CodebaseGraphPersistence(session).persist_graph(repo, nodes, [])
        session.execute(text("ANALYZE ingestion_service.document_nodes"))
        after = session.execute(
            text("""
            SELECT document_id FROM ingestion_service.document_nodes
            WHERE repo_id = :repo ORDER BY document_id OFFSET 3000 LIMIT 1
        """),
            {"repo": repo},
        ).scalar()
        plan = session.execute(
            text("""
            EXPLAIN (ANALYZE, BUFFERS, FORMAT JSON)
            SELECT document_id, canonical_id, relative_path, doc_type, text
            FROM ingestion_service.document_nodes
            WHERE repo_id = :repo AND ingestion_id = :attempt
              AND document_id > :after AND coalesce(octet_length(text), 0) <= 1048576
            ORDER BY document_id LIMIT 32
        """),
            {"repo": repo, "attempt": attempt, "after": after},
        ).scalar()
        print("PAGING_EXPLAIN=" + json.dumps(plan))
        assert plan[0]["Plan"]["Actual Rows"] == 32


@pytest.mark.skipif(sys.platform != "linux", reason="RSS probe requires Linux /proc")
def test_fresh_process_memory_scaling(vector_http_url, tmp_path):
    root = Path(__file__).resolve().parents[3]
    destination = Path(os.environ.get("MEMORY_ARTIFACT_DIR", str(tmp_path)))
    destination.mkdir(parents=True, exist_ok=True)
    summaries = []
    process_ids = []
    for label, files, chars in (
        ("N", 512, 1000),
        ("4N", 2048, 1000),
        ("large", 4, 128000),
    ):
        with (destination / f"{label}.jsonl").open("w", encoding="utf-8") as output:
            result = subprocess.run(
                [
                    sys.executable,
                    str(root / "scripts/benchmark_bounded_ingestion.py"),
                    "--files",
                    str(files),
                    "--payload-chars",
                    str(chars),
                    "--vector-url",
                    vector_http_url,
                ],
                cwd=root,
                stdout=output,
                stderr=subprocess.PIPE,
                text=True,
                timeout=300,
                check=False,
            )
        assert result.returncode == 0, result.stderr[-5000:]
        records = [
            json.loads(line)
            for line in (destination / f"{label}.jsonl").read_text().splitlines()
        ]
        environment = next(r for r in records if r["kind"] == "environment")
        summary = next(r for r in records if r["kind"] == "summary")
        process_ids.append(environment["pid"])
        assert summary["terminal"] == "completed"
        assert summary["chunks"] == summary["persisted"] > 0
        assert (
            summary["progress"]["max_buffer_chunks"]
            <= environment["buffer_count_limit"]
        )
        assert (
            summary["progress"]["max_buffer_bytes"] <= environment["buffer_byte_limit"]
        )
        assert summary["observed"]["max_page_nodes"] <= environment["page_limit"]
        assert (
            summary["observed"]["max_artifact_bytes"]
            <= environment["artifact_limit_bytes"]
        )
        assert {"graph_build", "graph_persist", "embedding", "completed"} <= set(
            summary["peak_rss_bytes"]
        )
        summaries.append(summary)
    assert len(set(process_ids)) == 3
    small, scaled, _ = summaries
    # SC-002 preregistered criterion; do not loosen after observing results.
    threshold = 1.5 * small["embedding_incremental_rss_bytes"] + 32 * 1024 * 1024
    result = {
        "criterion": "4N incremental RSS <= 1.5*N + 32 MiB",
        "N_files": 512,
        "4N_files": 2048,
        "summaries": summaries,
        "threshold_bytes": threshold,
        "passed": scaled["embedding_incremental_rss_bytes"] <= threshold,
        "scope": "synthetic graph/DB/HTTP with stub embedder; not DocsGPT/Ollama",
        "phase": os.environ.get("MEMORY_MEASUREMENT_PHASE", "calibration"),
    }
    (destination / "comparison.json").write_text(json.dumps(result, indent=2))
    print("MEMORY_COMPARISON=" + json.dumps(result))
    assert result["passed"]


def test_rebuild_graph_and_vector_parity_at_each_buffer_size(
    corpus,
    vector_http_url,
    tmp_path,
):
    """Compare independent real graph rebuilds, normalizing generated DB UUIDs."""
    from unittest.mock import Mock
    from src.api.v1 import codebase_ingest as api
    from src.core.config import Settings
    from src.core.http_vectorstore import HttpVectorStore
    from src.core.pipeline import IngestionPipeline
    from src.core.codebase.repo_graph_builder import RepoGraphBuilder

    (tmp_path / "a.py").write_text(
        "def target():\n    value = '" + "x" * 128000 + "'\n    return value\n",
    )
    (tmp_path / "b.py").write_text(
        "from a import target\n\ndef caller():\n    return target()\n",
    )
    repo, attempt, factory = corpus
    reference = RepoGraphBuilder(repo_root=tmp_path, ingestion_id=attempt).build()
    canonical_ids = {node["canonical_id"] for node in reference.all_entities()}
    expected_edges = {
        (rel["from_canonical_id"], rel["to_canonical_id"], rel["relation_type"])
        for rel in reference.relationships
        if rel["from_canonical_id"] in canonical_ids
        and rel["to_canonical_id"] in canonical_ids
    }
    assert any(edge[2] == "CALL" for edge in expected_edges)
    normalized_runs = []
    for buffer_size in (1, 7, 128):
        store = HttpVectorStore(vector_http_url)
        embedder = Mock()
        embedder.embed.side_effect = lambda chunks: [
            [float(len(chunk.content))] + [0.0] * 1023 for chunk in chunks
        ]
        pipeline = IngestionPipeline(
            validator=Mock(), embedder=embedder, vector_store=store
        )
        with factory() as session:
            persistence = CodebaseGraphPersistence(session)
            stats, _current_hashes = api._build_and_persist_graph(
                tmp_path,
                repo,
                attempt,
                persistence,
                lambda stage: None,
            )
            api._embed_repo_artifacts(
                pipeline,
                persistence,
                repo,
                attempt,
                stats["nodes"],
                "mock",
                Settings(
                    _env_file=None,
                    DATABASE_URL="unused",
                    INGESTION_EMBED_BATCH_SIZE=buffer_size,
                ),
                lambda progress: None,
            )
        with factory() as observer:
            nodes = observer.execute(
                text("""
                SELECT canonical_id, relative_path, doc_type, text
                FROM ingestion_service.document_nodes
                WHERE repo_id = :repo ORDER BY canonical_id
            """),
                {"repo": repo},
            ).all()
            edges = observer.execute(
                text("""
                SELECT a.canonical_id, b.canonical_id, r.relation_type
                FROM ingestion_service.document_relationships r
                JOIN ingestion_service.document_nodes a
                  ON a.document_id=r.from_document_id
                JOIN ingestion_service.document_nodes b
                  ON b.document_id=r.to_document_id
                WHERE a.repo_id = :repo ORDER BY 1, 2, 3
            """),
                {"repo": repo},
            ).all()
        assert {node.canonical_id for node in nodes} == canonical_ids
        assert set(map(tuple, edges)) == expected_edges
        normalized_runs.append((nodes, edges, _stored_vectors(factory, attempt)))
    assert normalized_runs[0] == normalized_runs[1] == normalized_runs[2]
