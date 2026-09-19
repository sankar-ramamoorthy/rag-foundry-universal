# ingestion_service/tests/api/test_incremental_deletes.py
"""
Issue #196, Phase 5 (US3): deletions are fully reflected, never orphaned.

T033: a file present in generation N but absent from generation N+1's
checkout has no document_nodes/document_relationships/vectors rows
referencing its canonical IDs (file-level or symbol-level) after N+1
completes (FR-008/SC-003).

T034: a symbol that a deleted file used to define, still referenced by
an unrelated *unchanged* file, resolves the same way a full rebuild
would (to an EXTERNAL_SYMBOL node), not to stale graph state -- proves
Phase 2's repo-scoped relationship replace (T011/R2) plus Phase 3's
always-on whole-repo re-resolution (FR-002) combine correctly for this
case.

Run with DATABASE_URL pointing at the test DB (localhost:5433), e.g.:
  DATABASE_URL=postgresql://...@localhost:5433/ingestion_test \
    ../.venv/Scripts/python.exe -m pytest \
    tests/api/test_incremental_deletes.py -m integration
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
from shared.models.document_relationship import DocumentRelationship
from src.core.pipeline import IngestionPipeline
from src.core.http_vectorstore import HttpVectorStore
from src.core.codebase.identity import build_repo_id

pytestmark = [pytest.mark.integration, pytest.mark.docker]


@pytest.fixture(scope="module")
def vector_http_url():
    """Real vector_store_service process, mirroring test_incremental_ingest.py."""
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


@pytest.fixture()
def repo_id(tmp_path):
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


def _node_rows(repo_id, canonical_ids):
    Session = get_sessionmaker()
    with Session() as s:
        return (
            s.query(DocumentNode)
            .filter(DocumentNode.repo_id == repo_id)
            .filter(DocumentNode.canonical_id.in_(canonical_ids))
            .all()
        )


def _relationship_count_for_document_ids(document_ids):
    if not document_ids:
        return 0
    Session = get_sessionmaker()
    with Session() as s:
        return (
            s.query(DocumentRelationship)
            .filter(
                (DocumentRelationship.from_document_id.in_(document_ids))
                | (DocumentRelationship.to_document_id.in_(document_ids))
            )
            .count()
        )


def _vector_count_for_document_ids(document_ids):
    if not document_ids:
        return 0
    Session = get_sessionmaker()
    with Session() as s:
        rows = s.execute(
            text(
                "SELECT count(*) FROM ingestion_service.vector_chunks "
                "WHERE document_id::text = ANY(:document_ids)"
            ),
            {"document_ids": [str(d) for d in document_ids]},
        ).scalar()
        return rows


def _relation_types(repo_id, document_id):
    Session = get_sessionmaker()
    with Session() as s:
        rows = (
            s.query(
                DocumentRelationship.relation_type,
                DocumentRelationship.to_document_id,
            )
            .filter(DocumentRelationship.from_document_id == document_id)
            .all()
        )
        return list(rows)


def _document_id(repo_id, canonical_id):
    Session = get_sessionmaker()
    with Session() as s:
        row = (
            s.query(DocumentNode)
            .filter_by(repo_id=repo_id, canonical_id=canonical_id)
            .one()
        )
        return row.document_id


# ---------------------------------------------------------------------
# T033: deleted file leaves no node/relationship/vector rows behind
# ---------------------------------------------------------------------

def test_deleted_file_leaves_no_orphaned_rows(
    monkeypatch, vector_http_url, repo_id, tmp_path,
):
    (tmp_path / "keep.py").write_text(
        "def keep():\n    return 1\n", encoding="utf-8",
    )
    (tmp_path / "stale.py").write_text(
        "def stale_fn():\n    return 2\n", encoding="utf-8",
    )

    id1 = uuid.uuid4()
    _run_ingestion(monkeypatch, vector_http_url, tmp_path, repo_id, id1)

    stale_file_doc_id = _document_id(repo_id, "stale.py")
    stale_symbol_doc_id = _document_id(repo_id, "stale.py#stale_fn")
    stale_doc_ids = [stale_file_doc_id, stale_symbol_doc_id]
    assert _vector_count_for_document_ids(stale_doc_ids) > 0, (
        "sanity: generation 1 actually embedded stale.py's vectors"
    )

    # Delete stale.py entirely; keep.py is untouched.
    (tmp_path / "stale.py").unlink()

    id2 = uuid.uuid4()
    _run_ingestion(monkeypatch, vector_http_url, tmp_path, repo_id, id2)
    req2 = _request_row(id2)
    assert req2.status == "completed"

    remaining = _node_rows(
        repo_id, ["stale.py", "stale.py#stale_fn"],
    )
    assert remaining == [], (
        "no document_nodes rows may reference the deleted file's "
        "canonical IDs (file-level or symbol-level) after re-ingestion"
    )
    assert _relationship_count_for_document_ids(stale_doc_ids) == 0, (
        "no document_relationships rows may reference the deleted rows' "
        "old document_ids"
    )
    assert _vector_count_for_document_ids(stale_doc_ids) == 0, (
        "no vectors rows may reference the deleted rows' old document_ids"
    )

    # keep.py is unaffected.
    assert _node_rows(repo_id, ["keep.py"]) != []


def _request_row(ingestion_id):
    Session = get_sessionmaker()
    with Session() as s:
        return s.get(IngestionRequest, ingestion_id)


# ---------------------------------------------------------------------
# T034: a caller of a deleted file's symbol re-resolves to EXTERNAL_SYMBOL,
# matching what a full rebuild from the same post-delete checkout would
# produce -- not stale graph state.
# ---------------------------------------------------------------------

def test_caller_of_deleted_symbol_reresolves_to_external(
    monkeypatch, vector_http_url, repo_id, tmp_path,
):
    (tmp_path / "lib.py").write_text(
        "def helper():\n    return 1\n", encoding="utf-8",
    )
    # Bare, unqualified call to a same-repo, globally-unique symbol --
    # resolves via ADR-032's global-index tier (priority 4) as long as
    # lib.py's helper() exists.
    (tmp_path / "caller.py").write_text(
        "def use_helper():\n    return helper()\n", encoding="utf-8",
    )

    id1 = uuid.uuid4()
    _run_ingestion(monkeypatch, vector_http_url, tmp_path, repo_id, id1)

    caller_doc_id = _document_id(repo_id, "caller.py#use_helper")
    edges_before = _relation_types(repo_id, caller_doc_id)
    call_targets_before = {
        to_id for (rel_type, to_id) in edges_before if rel_type == "CALL"
    }
    helper_doc_id = _document_id(repo_id, "lib.py#helper")
    assert helper_doc_id in call_targets_before, (
        "sanity: generation 1 must resolve the bare call to lib.py's helper()"
    )

    # Delete lib.py; caller.py is untouched (unchanged content).
    (tmp_path / "lib.py").unlink()

    id2 = uuid.uuid4()
    _run_ingestion(monkeypatch, vector_http_url, tmp_path, repo_id, id2)
    req2 = _request_row(id2)
    assert req2.status == "completed"

    # caller.py's own node is unchanged (reused document_id, R1) -- this
    # specifically exercises the "reused-but-unaffected node, edges must
    # still be re-resolved" case, not a node-cascade side effect.
    assert _document_id(repo_id, "caller.py#use_helper") == caller_doc_id

    edges_after = _relation_types(repo_id, caller_doc_id)
    call_edges_after = [
        (rel_type, to_id) for (rel_type, to_id) in edges_after if rel_type == "CALL"
    ]
    assert len(call_edges_after) == 1, (
        f"expected exactly one CALL edge from caller.py#use_helper after "
        f"lib.py's deletion, got {call_edges_after}"
    )
    (_, resolved_to_id) = call_edges_after[0]
    Session = get_sessionmaker()
    with Session() as s:
        resolved_node = s.get(DocumentNode, resolved_to_id)
    assert resolved_node.canonical_id.startswith("EXTERNAL_SYMBOL:"), (
        "with lib.py gone, caller.py's call to helper() must re-resolve "
        "to an EXTERNAL_SYMBOL node -- exactly what a full rebuild of the "
        "post-delete checkout would produce -- not remain pinned to the "
        "stale lib.py#helper target"
    )
