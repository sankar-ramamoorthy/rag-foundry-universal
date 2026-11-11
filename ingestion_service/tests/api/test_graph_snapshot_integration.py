"""CI-01 / #335: actual PostgreSQL snapshot and HTTP contract acceptance."""

import uuid
import asyncio
import json
import os
import socket
import subprocess
import sys
import time
from pathlib import Path
from queue import Queue
from threading import Thread
from concurrent.futures import ThreadPoolExecutor
from threading import Event, current_thread
from time import monotonic

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from shared.models.document_node import DocumentNode
from src.api.v1 import graph, repos
from src.core import db_utils
from src.core.codebase.codebase_persistence import CodebaseGraphPersistence
from src.core.database_session import get_sessionmaker
from src.core.database_session import get_engine, read_snapshot
from src.core.models import IngestionRequest
from src.core.status_manager import StatusManager
from sqlalchemy import event, text
from sqlalchemy.exc import OperationalError, MultipleResultsFound
import httpx
import requests

pytestmark = [pytest.mark.integration, pytest.mark.docker]


@pytest.fixture
def repo_id():
    rid = str(uuid.uuid4())
    yield rid
    with get_sessionmaker()() as session:
        session.query(DocumentNode).filter_by(repo_id=rid).delete()
        session.query(IngestionRequest).filter_by(repo_id=rid).delete()
        session.commit()


@pytest.fixture
def client():
    app = FastAPI()
    app.include_router(graph.router, prefix="/v1")
    app.include_router(repos.router, prefix="/v1")
    return TestClient(app)


def publish(repo_id, tag, *, complete=True, edges=True):
    generation = uuid.uuid4()
    with get_sessionmaker()() as session:
        status = StatusManager(session)
        status.create_request(
            ingestion_id=generation,
            repo_id=repo_id,
            source_type="repo",
            metadata={},
        )
        status.mark_running(generation)
        CodebaseGraphPersistence(session=session).persist_graph(
            repo_id=repo_id,
            nodes=[
                {
                    "canonical_id": cid,
                    "relative_path": "a.py",
                    "title": tag,
                    "doc_type": "code",
                    "source": "a.py",
                    "summary": "",
                    "text": tag,
                    "ingestion_id": str(generation),
                }
                for cid in ("a.py#f", "a.py#g")
            ],
            relationships=[
                {
                    "from_canonical_id": "a.py#f",
                    "to_canonical_id": "a.py#g",
                    "relation_type": "CALL",
                    "relationship_metadata": {"tag": tag},
                }
            ]
            if edges
            else [],
        )
        if complete:
            status.mark_completed(generation)
    return str(generation)


def test_ready_identity_and_expected_generation(client, repo_id):
    generation = publish(repo_id, "A")
    response = client.get(
        f"/v1/graph/repos/{repo_id}",
        params={
            "expected_generation_id": generation,
        },
    )
    assert response.status_code == 200
    body = response.json()
    assert (body["repo_id"], body["ingestion_id"], body["generation_status"]) == (
        repo_id,
        generation,
        "ready",
    )
    assert body["total_nodes"] == len(body["nodes"]) == 2
    assert body["relationships"]["a.py#f"][0]["relationship_metadata"] == {"tag": "A"}
    conflict = client.get(
        f"/v1/graph/repos/{repo_id}",
        params={
            "expected_generation_id": str(uuid.uuid4()),
        },
    )
    assert conflict.status_code == 409
    assert conflict.json()["detail"]["ingestion_id"] == generation
    assert "nodes" not in conflict.json()["detail"]


def test_no_nodes_cannot_be_ready(client, repo_id):
    body = client.get(f"/v1/graph/repos/{repo_id}").json()
    assert body["generation_status"] == "unknown"
    assert body["ingestion_id"] is None
    assert body["nodes"] == []


def test_rebuild_after_owner_read_preserves_snapshot(monkeypatch, repo_id):
    generation = publish(repo_id, "A")
    original = db_utils._document_node_owner

    def read_owner_then_publish(session, rid):
        owner = original(session, rid)
        publish(rid, "B")  # Separate connection commits before reader's next SQL.
        return owner

    monkeypatch.setattr(db_utils, "_document_node_owner", read_owner_then_publish)
    body = db_utils.get_full_graph_for_repo(repo_id)
    assert body["ingestion_id"] == generation
    assert {node["title"] for node in body["nodes"].values()} == {"A"}
    assert body["relationships"]["a.py#f"][0]["relationship_metadata"] == {"tag": "A"}


@pytest.mark.parametrize("boundary", ["owner", "nodes"])
@pytest.mark.parametrize("mutation", ["rebuild", "delete", "cleanup"])
def test_concurrent_commit_cannot_mix_graph_versions(
    monkeypatch,
    repo_id,
    boundary,
    mutation,
):
    generation = publish(repo_id, "A")
    before_ids = {
        cid: node["document_id"]
        for cid, node in db_utils.get_full_graph_for_repo(repo_id)["nodes"].items()
    }
    reached, resume = Event(), Event()
    original = db_utils._document_node_owner
    engine = get_engine()

    def pause():
        reached.set()
        assert resume.wait(15), "writer failed to release reader"

    def owner(session, rid):
        value = original(session, rid)
        if boundary == "owner" and current_thread().name.startswith("ci01-reader"):
            pause()
        return value

    def after_sql(conn, cursor, statement, params, context, many):
        if (
            boundary == "nodes"
            and current_thread().name.startswith("ci01-reader")
            and statement.startswith("SELECT ")
            and "document_nodes.provenance" in statement
        ):
            pause()

    monkeypatch.setattr(db_utils, "_document_node_owner", owner)
    event.listen(engine, "after_cursor_execute", after_sql)
    try:
        with ThreadPoolExecutor(thread_name_prefix="ci01-reader") as pool:
            future = pool.submit(db_utils.get_full_graph_for_repo, repo_id, generation)
            try:
                assert reached.wait(10), "reader did not reach SQL barrier"
                if mutation == "delete":
                    with get_sessionmaker()() as writer:
                        writer.query(DocumentNode).filter_by(repo_id=repo_id).delete()
                        writer.query(IngestionRequest).filter_by(
                            repo_id=repo_id
                        ).delete()
                        writer.commit()
                else:
                    publish(repo_id, "B")
                    if mutation == "cleanup":
                        db_utils.delete_ingestion_requests([generation])
            finally:
                resume.set()
            result = future.result(timeout=10)
    finally:
        event.remove(engine, "after_cursor_execute", after_sql)
    assert result["ingestion_id"] == generation
    assert {n["title"] for n in result["nodes"].values()} == {"A"}
    assert result["relationships"]["a.py#f"][0]["relationship_metadata"] == {"tag": "A"}
    if mutation != "delete":
        after = db_utils.get_full_graph_for_repo(repo_id)
        assert before_ids == {
            cid: n["document_id"] for cid, n in after["nodes"].items()
        }
        assert {n["title"] for n in after["nodes"].values()} == {"B"}


def test_completion_committed_mid_read_remains_unavailable(monkeypatch, repo_id):
    generation = publish(repo_id, "B", complete=False)
    original = db_utils._document_node_owner

    def complete_after_owner(session, rid):
        owner = original(session, rid)
        with get_sessionmaker()() as writer:
            StatusManager(writer).mark_completed(uuid.UUID(generation))
        return owner

    monkeypatch.setattr(db_utils, "_document_node_owner", complete_after_owner)
    result = db_utils.get_full_graph_for_repo(repo_id, generation)
    assert result["generation_status"] == "building"
    assert result["ingestion_id"] is None
    assert result["nodes"] == result["relationships"] == {}
    monkeypatch.setattr(db_utils, "_document_node_owner", original)
    assert db_utils.get_full_graph_for_repo(repo_id)["ingestion_id"] == generation


@pytest.mark.parametrize("status", ["accepted", "running", "failed", "completed"])
@pytest.mark.parametrize("has_nodes", [False, True])
def test_availability_precedence(client, repo_id, status, has_nodes):
    generation = publish(repo_id, "A", complete=False)
    with get_sessionmaker()() as writer:
        writer.query(IngestionRequest).filter_by(ingestion_id=generation).update(
            {"status": status},
            synchronize_session=False,
        )
        if not has_nodes:
            writer.query(DocumentNode).filter_by(repo_id=repo_id).delete()
        writer.commit()
    expected = (
        ("ready" if has_nodes else "unknown")
        if status == "completed"
        else ("failed" if status == "failed" else "building")
    )
    response = client.get(
        f"/v1/graph/repos/{repo_id}",
        params={
            "expected_generation_id": generation,
        },
    )
    assert response.status_code == 200
    body = response.json()
    assert body["generation_status"] == expected
    if expected != "ready":
        assert body["ingestion_id"] is None
        assert body["total_nodes"] == 0
        assert body["nodes"] == [] and body["relationships"] == {}


def test_newer_failed_attempt_leaves_completed_owner_servable(repo_id):
    generation = publish(repo_id, "A", edges=False)
    with get_sessionmaker()() as writer:
        failed = uuid.uuid4()
        manager = StatusManager(writer)
        manager.create_request(
            ingestion_id=failed,
            repo_id=repo_id,
            source_type="repo",
            metadata={},
        )
        manager.mark_failed(failed)
    result = db_utils.get_full_graph_for_repo(repo_id)
    assert result["ingestion_id"] == generation
    assert result["relationships"] == {}


def test_writer_rollback_leaves_published_snapshot(repo_id):
    generation = publish(repo_id, "A")
    with read_snapshot() as reader:
        assert str(db_utils._document_node_owner(reader, repo_id)) == generation
        with get_sessionmaker()() as writer:
            writer.query(DocumentNode).filter_by(repo_id=repo_id).update(
                {"title": "uncommitted"},
                synchronize_session=False,
            )
            writer.query(DocumentNode).filter_by(repo_id=repo_id).delete()
            writer.rollback()
        assert {
            n.title for n in reader.query(DocumentNode).filter_by(repo_id=repo_id)
        } == {"A"}
    assert db_utils.get_full_graph_for_repo(repo_id)["ingestion_id"] == generation


def test_effective_isolation_cleanup_and_writer_pool_settings(repo_id):
    engine = get_engine()
    before = engine.pool.checkedout()
    with read_snapshot() as session:
        assert (
            session.execute(text("SHOW transaction_isolation")).scalar()
            == "repeatable read"
        )
        assert session.execute(text("SHOW transaction_read_only")).scalar() == "on"
    assert engine.pool.checkedout() == before
    with pytest.raises(RuntimeError):
        with read_snapshot() as session:
            session.execute(text("SELECT 1"))
            raise RuntimeError("injected failure")
    assert engine.pool.checkedout() == before
    with get_sessionmaker()() as writer:
        assert (
            writer.execute(text("SHOW transaction_isolation")).scalar()
            == "read committed"
        )
        assert writer.execute(text("SHOW transaction_read_only")).scalar() == "off"
        assert writer.execute(text("SHOW statement_timeout")).scalar() == "0"
        writer.rollback()
    publish(repo_id, "A")  # Normal writer remains usable after pooled reads.


def test_database_timeout_releases_reader(monkeypatch, repo_id):
    publish(repo_id, "A")
    engine = get_engine()
    before = engine.pool.checkedout()
    monkeypatch.setattr(db_utils.get_settings(), "GRAPH_EXPORT_TIMEOUT_SECONDS", 0.05)
    original = db_utils._document_node_owner

    def slow_owner(session, rid):
        session.execute(text("SELECT pg_sleep(1)"))
        return original(session, rid)

    monkeypatch.setattr(db_utils, "_document_node_owner", slow_owner)
    started = monotonic()
    with pytest.raises(OperationalError):
        db_utils.get_full_graph_for_repo(repo_id)
    assert monotonic() - started < 1
    assert engine.pool.checkedout() == before


def test_unknown_owner_and_multiple_owners_fail_closed(monkeypatch, client, repo_id):
    generation = publish(repo_id, "A")
    # Missing requests are prevented by FK in healthy storage; exercise the
    # resolver seam without disabling constraints in the database.
    monkeypatch.setattr(
        db_utils, "_document_node_owner", lambda session, rid: str(uuid.uuid4())
    )
    assert (
        client.get(f"/v1/graph/repos/{repo_id}").json()["generation_status"]
        == "unknown"
    )
    monkeypatch.undo()
    with get_sessionmaker()() as writer:
        other = uuid.uuid4()
        StatusManager(writer).create_request(
            ingestion_id=other,
            repo_id=repo_id,
            source_type="repo",
            metadata={},
        )
        writer.query(DocumentNode).filter_by(
            repo_id=repo_id, canonical_id="a.py#g"
        ).update(
            {"ingestion_id": str(other)},
            synchronize_session=False,
        )
        writer.commit()
    with pytest.raises(MultipleResultsFound):
        db_utils.get_full_graph_for_repo(repo_id, generation)


def test_malformed_expectation_is_422(client, repo_id):
    response = client.get(
        f"/v1/graph/repos/{repo_id}", params={"expected_generation_id": "bad"}
    )
    assert response.status_code == 422


def test_abandoned_http_reader_releases_connection(monkeypatch, repo_id):
    publish(repo_id, "A")
    engine = get_engine()
    before = engine.pool.checkedout()
    reached, finished = Event(), Event()
    monkeypatch.setattr(db_utils.get_settings(), "GRAPH_EXPORT_TIMEOUT_SECONDS", 0.1)

    def slow_owner(session, rid):
        reached.set()
        try:
            session.execute(text("SELECT pg_sleep(2)"))
        finally:
            finished.set()

    monkeypatch.setattr(db_utils, "_document_node_owner", slow_owner)
    app = FastAPI()
    app.include_router(graph.router, prefix="/v1")

    async def abandon():
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app),
            base_url="http://test",
        ) as client:
            task = asyncio.create_task(client.get(f"/v1/graph/repos/{repo_id}"))
            assert await asyncio.to_thread(reached.wait, 5)
            task.cancel()
            with pytest.raises(asyncio.CancelledError):
                await task
            assert await asyncio.to_thread(finished.wait, 5)
            deadline = monotonic() + 3
            while engine.pool.checkedout() != before and monotonic() < deadline:
                await asyncio.sleep(0.01)

    asyncio.run(abandon())
    assert engine.pool.checkedout() == before


@pytest.fixture
def producer_http():
    """Real HTTP ingestion routes in a separate process, no inference services."""
    root = Path(__file__).resolve().parents[3]
    with socket.socket() as reserved:
        reserved.bind(("127.0.0.1", 0))
        port = reserved.getsockname()[1]
    code = (
        "from fastapi import FastAPI; import uvicorn; "
        "from src.api.v1 import graph, repos; app=FastAPI(); "
        "app.include_router(graph.router,prefix='/v1'); "
        "app.include_router(repos.router,prefix='/v1'); "
        f"uvicorn.run(app,host='127.0.0.1',port={port},log_level='error')"
    )
    process = subprocess.Popen(
        [sys.executable, "-c", code],
        cwd=root / "ingestion_service",
        env={**os.environ, "PYTHONPATH": str(root)},
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    url = f"http://127.0.0.1:{port}"
    try:
        deadline = monotonic() + 20
        while monotonic() < deadline:
            assert process.poll() is None, "producer failed to start"
            try:
                if requests.get(url + "/openapi.json", timeout=0.5).status_code == 200:
                    break
            except requests.RequestException:
                pass
            time.sleep(0.05)  # Startup only; concurrency tests use explicit barriers.
        else:
            pytest.fail("producer HTTP startup deadline exceeded")
        yield url
    finally:
        process.terminate()
        try:
            process.wait(timeout=5)
        except subprocess.TimeoutExpired:
            process.kill()
            process.wait(timeout=5)


@pytest.mark.parametrize("replacement_ready", [True, False])
def test_real_http_lookup_export_race(producer_http, repo_id, replacement_ready):
    """Actual route -> requests -> loader -> cache, with real PostgreSQL writes."""
    generation = publish(repo_id, "A")
    root = Path(__file__).resolve().parents[3]
    code = f"""
import json
from src.retrieval import codebase_utils as cache
from src.retrieval.codebase_queries import GraphSnapshotError
original = cache.get_repo_generation
def lookup(repo):
    result = original(repo)
    print(json.dumps({{"lookup": result[0]}}), flush=True)
    input()
    return result
cache.get_repo_generation = lookup
try:
    cache.get_cached_graph_with_generation({repo_id!r})
    raise AssertionError("race unexpectedly returned a graph")
except GraphSnapshotError as exc:
    print(json.dumps({{"status": exc.status_code, "cached": bool(cache._repo_graphs)}}))
"""
    process = subprocess.Popen(
        [sys.executable, "-u", "-c", code],
        cwd=root / "rag_orchestrator",
        env={
            **os.environ,
            "PYTHONPATH": str(root),
            "INGESTION_SERVICE_URL": producer_http,
        },
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )
    lines = Queue()
    assert process.stdout is not None
    output_stream = process.stdout
    Thread(target=lambda: lines.put(output_stream.readline()), daemon=True).start()
    try:
        assert json.loads(lines.get(timeout=10))["lookup"] == generation
        publish(repo_id, "B", complete=replacement_ready)
        output, error = process.communicate(input="\n", timeout=15)
        assert process.returncode == 0, error
        assert json.loads(output) == {
            "status": 409 if replacement_ready else 503,
            "cached": False,
        }
    finally:
        if process.poll() is None:
            process.kill()
            process.wait(timeout=5)


def test_real_http_stable_warm_force_reload(producer_http, repo_id):
    generation = publish(repo_id, "A")
    root = Path(__file__).resolve().parents[3]
    code = f"""
from src.retrieval import codebase_utils as cache, codebase_queries as queries
original = queries.requests.get
exports = []
def get(url, **kwargs):
    if '/graph/repos/' in url:
        exports.append(kwargs['params']['expected_generation_id'])
    return original(url, **kwargs)
queries.requests.get = get
first = cache.get_cached_graph_with_generation({repo_id!r})
assert first[0] == first[1].ingestion_id == {generation!r}
assert cache.get_cached_graph_with_generation({repo_id!r})[1] is first[1]
assert exports == [{generation!r}]
forced = cache.get_cached_graph_with_generation({repo_id!r}, force_reload=True)
assert forced[1] is not first[1]
assert exports == [{generation!r}, {generation!r}]
print('PASS')
"""
    result = subprocess.run(
        [sys.executable, "-c", code],
        cwd=root / "rag_orchestrator",
        env={
            **os.environ,
            "PYTHONPATH": str(root),
            "INGESTION_SERVICE_URL": producer_http,
        },
        capture_output=True,
        text=True,
        timeout=20,
    )
    assert result.returncode == 0, result.stderr
    assert result.stdout.strip() == "PASS"
