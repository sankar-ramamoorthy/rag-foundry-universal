"""#379 HTTP contract and real PostgreSQL lifecycle/concurrency acceptance.

Only run against an explicitly local *_test database. Never write to production.
"""

import hashlib
import uuid
from concurrent.futures import ThreadPoolExecutor
from threading import Event
from urllib.parse import urlparse

import httpx
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import select, text
from sqlalchemy.exc import DBAPIError

from shared.models.document_node import DocumentNode
from src.api.errors import register_error_handlers
from src.api.v1 import source_navigation as api
from src.core import source_navigation as source
from src.core.codebase.codebase_persistence import CodebaseGraphPersistence
from src.core.config import get_settings
from src.core.database_session import get_sessionmaker
from src.core.models import IngestionRequest
from src.core.status_manager import StatusManager

pytestmark = [pytest.mark.integration, pytest.mark.docker]


@pytest.fixture
def repos():
    parsed = urlparse(get_settings().DATABASE_URL)
    assert parsed.path.endswith("_test"), "Refusing writes outside a test database"
    assert parsed.hostname in ("localhost", "127.0.0.1", "postgres")
    ids = [str(uuid.uuid4()), str(uuid.uuid4())]
    yield ids
    factory = get_sessionmaker()
    assert factory is not None
    with factory() as session:
        for repo_id in ids:
            session.query(DocumentNode).filter_by(repo_id=repo_id).delete()
            session.query(IngestionRequest).filter_by(repo_id=repo_id).delete()
        session.commit()


@pytest.fixture
def app():
    app = FastAPI()
    register_error_handlers(app)
    app.include_router(api.router, prefix="/v1")

    @app.get("/ping")
    async def ping():
        return {"ok": True}

    return app


@pytest.fixture
def client(app):
    return TestClient(app)


def publish(repo, files, status="completed"):
    gen = uuid.uuid4()
    with get_sessionmaker()() as session:
        manager = StatusManager(session)
        manager.create_request(
            ingestion_id=gen, source_type="repo", metadata={}, repo_id=repo
        )
        manager.mark_running(gen)
        nodes = []
        for path, content, doc_type in files:
            nodes.append(
                {
                    "canonical_id": path,
                    "relative_path": path.split("#")[0],
                    "doc_type": doc_type,
                    "title": path,
                    "source": path,
                    "summary": "",
                    "text": content,
                    "ingestion_id": str(gen),
                }
            )
        CodebaseGraphPersistence(session=session).persist_graph(repo, nodes, [])
        if status == "completed":
            manager.mark_completed(gen)
        elif status == "failed":
            manager.mark_failed(gen)
    return str(gen)


def read(client, repo, gen, path="a.py", **params):
    return client.get(
        f"/v1/repos/{repo}/source/read",
        params={
            "generation_id": gen,
            "path": path,
            **params,
        },
    )


def files(client, repo, gen, **params):
    return client.get(
        f"/v1/repos/{repo}/source/files",
        params={
            "generation_id": gen,
            **params,
        },
    )


def test_source_identity_empty_structural_symbols_and_repository_isolation(
    client, repos
):
    a, b = repos
    ga = publish(
        a,
        [
            ("a.py", "def f():\n    return 'é'\n", "python source"),
            ("a.py#f", "not a module", "python source"),
            ("empty.py", "", "python source"),
            ("null.py", None, "python source"),
            ("Dockerfile", "", "file"),
            ("legacy.py", "unknown representation", "unknown"),
        ],
    )
    gb = publish(b, [("a.py", "other repository", "python source")])
    response = files(client, a, ga)
    assert response.status_code == 200
    rows = {f["path"]: f for f in response.json()["files"]}
    assert "a.py#f" not in rows
    assert rows["a.py"]["source_status"] == "available"
    assert rows["empty.py"]["source_status"] == "available"
    for name in ("null.py", "Dockerfile", "legacy.py"):
        assert rows[name]["source_status"] == "unavailable"
        assert read(client, a, ga, name).status_code == 422
    body = read(client, a, ga).json()
    assert body["text"] == "def f():\n    return 'é'\n"
    assert body["text_sha256"] == hashlib.sha256(body["text"].encode()).hexdigest()
    assert body["total_lines"] == 2 and body["complete_file"]
    assert read(client, b, gb).json()["text"] == "other repository"
    assert read(client, a, gb).status_code == 409
    assert read(client, a, ga, "a.py#f").status_code == 404
    assert read(client, a, ga, "missing.py").status_code == 404
    empty = read(client, a, ga, "empty.py").json()
    assert (
        empty["text"],
        empty["start_line"],
        empty["end_line"],
        empty["total_lines"],
        empty["complete_file"],
    ) == ("", 0, 0, 0, True)
    assert read(client, a, ga, "empty.py", start_line=1).status_code == 416


def test_discovery_paging_globs_case_literal_metacharacters_and_bound_cursors(
    client, repos
):
    repo = repos[0]
    paths = ["a.py", "A.py", "src/a.py", "src/é.py", "src/deep/z.py", "[1]%.py"]
    gen = publish(repo, [(path, path, "python source") for path in paths])
    seen, cursor = [], None
    while True:
        response = files(
            client,
            repo,
            gen,
            pattern="**/*.py",
            limit=2,
            **({"cursor": cursor} if cursor else {}),
        )
        assert response.status_code == 200
        body = response.json()
        seen.extend(row["path"] for row in body["files"])
        cursor = body["next_cursor"]
        if cursor is None:
            break
    assert seen == sorted(paths, key=lambda s: s.encode())
    assert [
        r["path"] for r in files(client, repo, gen, pattern="[1]%.py").json()["files"]
    ] == ["[1]%.py"]
    assert len(files(client, repo, gen, pattern="*.py").json()["files"]) == 3
    cursor = files(client, repo, gen, limit=1).json()["next_cursor"]
    assert files(client, repo, gen, cursor=cursor, pattern="*.py").status_code == 400
    next_gen = publish(repo, [("new.py", "new", "python source")])
    assert files(client, repo, gen, cursor=cursor).status_code == 409
    assert files(client, repo, next_gen, cursor=cursor).status_code == 400


@pytest.mark.parametrize(
    "content", ["\n\né\n中\n", "a\r\nb\nlast", "a\vb\u2028c\nlast"]
)
def test_exact_ranges_preserve_characters_and_hashes(client, repos, content):
    repo = repos[0]
    gen = publish(repo, [("a.py", content, "python source")])
    line_count = content.count("\n") + (not content.endswith("\n"))
    pieces = [
        read(client, repo, gen, start_line=i, end_line=i).json()["text"]
        for i in range(1, line_count + 1)
    ]
    assert "".join(pieces) == content
    partial = read(client, repo, gen, start_line=1, end_line=1).json()
    assert partial["text_sha256"] is None and partial["total_lines"] is None
    assert partial["next_start_line"] == 2
    assert (
        partial["returned_text_sha256"]
        == hashlib.sha256(pieces[0].encode()).hexdigest()
    )
    assert (
        read(client, repo, gen, start_line=line_count, end_line=500).json()["end_line"]
        == line_count
    )
    assert read(client, repo, gen, start_line=500).status_code == 416
    assert read(client, repo, gen, start_line=0).status_code == 416
    assert read(client, repo, gen, start_line=1, end_line=501).status_code == 413


@pytest.mark.parametrize("status", ["running", "failed"])
def test_incomplete_replacement_never_falls_back_to_old_source(client, repos, status):
    repo = repos[0]
    old = publish(repo, [("a.py", "old", "python source")])
    new = publish(repo, [("a.py", "incomplete", "python source")], status=status)
    for gen in (old, new):
        response = read(client, repo, gen)
        assert response.status_code == 404
        assert response.json()["error_code"] == "GENERATION_UNAVAILABLE"
        assert "text" not in response.json()


def test_5_mib_file_early_read_succeeds_late_read_explicitly_exhausts(client, repos):
    repo = repos[0]
    content = ("x" * 63 + "\n") * 81921
    assert len(content.encode()) > 5 * 1024 * 1024
    gen = publish(repo, [("a.py", content, "python source")])
    early = read(client, repo, gen, start_line=1, end_line=10)
    assert early.status_code == 200 and early.json()["text"] == content[:640]
    late = read(client, repo, gen, start_line=81900)
    assert late.status_code == 413
    assert late.json()["error_code"] == "SCAN_LIMIT_EXCEEDED"
    assert "text" not in late.json()
    assert read(client, repo, gen).json()["error_code"] == "READ_TOO_LARGE"


def test_full_read_line_text_and_serialized_response_caps(client, repos):
    repo = repos[0]
    gen = publish(
        repo,
        [
            ("a.py", "\x01" * 50000, "python source"),
            ("lines.py", "x\n" * 501, "python source"),
            ("giant.py", "é" * 65537, "python source"),
            ("boundary.py", "x" * 131071 + "\n", "python source"),
        ],
    )
    assert read(client, repo, gen).json()["error_code"] == "RESPONSE_TOO_LARGE"
    assert read(client, repo, gen, "lines.py").json()["error_code"] == "READ_TOO_LARGE"
    assert read(client, repo, gen, "lines.py", start_line=1).json()["end_line"] == 500
    assert (
        read(client, repo, gen, "giant.py", start_line=1).json()["error_code"]
        == "READ_TOO_LARGE"
    )
    boundary = read(client, repo, gen, "boundary.py")
    assert (
        boundary.status_code == 200 and len(boundary.json()["text"].encode()) == 131072
    )


@pytest.mark.parametrize("mutation", ["rebuild", "delete"])
@pytest.mark.parametrize("boundary", ["owner", "window"])
def test_committed_writer_cannot_mix_inflight_source_snapshot(
    monkeypatch, client, repos, mutation, boundary
):
    repo = repos[0]
    old = publish(repo, [("a.py", "old\n" * 15000, "python source")])
    entered, resume = Event(), Event()
    original = source.ready_generation

    def pause(session, rid, expected, budget):
        value = original(session, rid, expected, budget)
        if boundary == "owner":
            entered.set()
            assert resume.wait(3)
        return value

    monkeypatch.setattr(source, "ready_generation", pause)
    original_execute = source.Budget.execute

    def execute(budget, session, statement):
        result = original_execute(budget, session, statement)
        if boundary == "window" and "substr(" in str(statement):
            entered.set()
            assert resume.wait(3)
        return result

    monkeypatch.setattr(source.Budget, "execute", execute)
    with ThreadPoolExecutor() as executor:
        future = executor.submit(read, client, repo, old, start_line=14900)
        assert entered.wait(3)
        if mutation == "rebuild":
            publish(repo, [("a.py", "new", "python source")])
        else:
            with get_sessionmaker()() as session:
                session.query(DocumentNode).filter_by(repo_id=repo).delete()
                session.query(IngestionRequest).filter_by(repo_id=repo).delete()
                session.commit()
        resume.set()
        response = future.result(timeout=5)
    assert response.status_code == 200 and response.json()["text"] == "old\n" * 101
    assert response.json()["generation_id"] == old
    monkeypatch.setattr(source, "ready_generation", original)
    assert read(client, repo, old).status_code == (
        409 if mutation == "rebuild" else 404
    )


@pytest.mark.asyncio
async def test_slow_database_read_has_live_timeout_and_does_not_block_ping(
    monkeypatch, app, repos
):
    import asyncio

    repo = repos[0]
    gen = publish(repo, [("a.py", "source", "python source")])
    original = source.ready_generation

    def slow(session, rid, expected, budget):
        budget.execute(session, select(func_pg_sleep()))
        return original(session, rid, expected, budget)

    monkeypatch.setattr(source, "SECONDS", 0.15)
    monkeypatch.setattr(source, "ready_generation", slow)
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://test"
    ) as client:
        request = asyncio.create_task(
            client.get(
                f"/v1/repos/{repo}/source/read",
                params={"generation_id": gen, "path": "a.py"},
            )
        )
        await asyncio.sleep(0.03)
        ping = await asyncio.wait_for(client.get("/ping"), timeout=0.1)
        assert ping.json() == {"ok": True}
        response = await asyncio.wait_for(request, timeout=1)
    assert response.status_code == 503
    assert response.json()["error_code"] == "DEADLINE_EXCEEDED"


def func_pg_sleep():
    return text("pg_sleep(0.6)")


def test_source_pool_uses_readonly_repeatable_read_and_cannot_write(repos):
    with pytest.raises(DBAPIError) as error:
        with source.snapshot() as session:
            settings = session.execute(
                text(
                    "SELECT current_setting('transaction_read_only'), "
                    "current_setting('transaction_isolation')"
                )
            ).one()
            assert tuple(settings) == ("on", "repeatable read")
            session.execute(
                text(
                    "UPDATE ingestion_service.document_nodes SET text=text WHERE false"
                )
            )
    assert getattr(error.value.orig, "pgcode", None) == "25006"


def test_new_and_missing_repositories_have_distinct_explicit_failures(client, repos):
    repo = repos[0]
    gen = uuid.uuid4()
    assert read(client, repo, str(gen)).json()["error_code"] == "REPOSITORY_NOT_FOUND"
    with get_sessionmaker()() as session:
        StatusManager(session).create_request(
            ingestion_id=gen,
            source_type="repo",
            metadata={},
            repo_id=repo,
        )
    pending = read(client, repo, str(gen))
    assert pending.status_code == 404
    assert pending.json()["error_code"] == "GENERATION_UNAVAILABLE"
    assert pending.json()["details"]["generation_status"] == "building"
