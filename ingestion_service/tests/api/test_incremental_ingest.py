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


def _vector_source_metadata(document_id):
    Session = get_sessionmaker()
    with Session() as s:
        rows = s.execute(
            text(
                "SELECT source_metadata FROM ingestion_service.vector_chunks "
                "WHERE document_id = :document_id"
            ),
            {"document_id": document_id},
        ).all()
        return [r[0] for r in rows]


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
# Issue #199 (Stage B2 incremental-reuse fix): a reused (not re-embedded)
# artifact's vector-level provenance must still track the current
# classifier's output, exactly like DocumentNode.provenance already does
# (Stage B1). Root cause found via a real production incremental ingest
# (see DOCS/test_results/2026-09-19-stage-c-authority-aware-sufficiency.md's
# follow-up note): the reuse path retagged ingestion_id but never touched
# source_metadata, so /v1/rag's manifest silently read stale/unknown
# provenance for anything an incremental generation didn't re-embed.
# ---------------------------------------------------------------------

def test_reused_vector_provenance_refreshed_without_reembed(
    monkeypatch, vector_http_url, repo_id, tmp_path,
):
    _write_repo(tmp_path, "def touch():\n    return 1\n")

    id1 = uuid.uuid4()
    _run_ingestion(monkeypatch, vector_http_url, tmp_path, repo_id, id1)

    keep_doc_id = _document_id(repo_id, "keep.py")
    original_metadata = _vector_source_metadata(keep_doc_id)
    assert original_metadata, "keep.py must have persisted vector rows"
    original_provenance = original_metadata[0]["provenance"]
    assert original_provenance["role"]["value"] == "implementation"
    original_canonical_id = original_metadata[0]["canonical_id"]

    # Edit touch.py only; keep.py's bytes stay untouched, so it is reuse-
    # eligible on the next generation -- exactly the path that skipped
    # provenance entirely before this fix.
    (tmp_path / "touch.py").write_text("def touch():\n    return 2\n", encoding="utf-8")

    # Simulate a classifier-version bump (spec 008 FR-005): keep.py's
    # bytes/path/doc_type are unchanged, but the classifier's output for
    # it is different now.
    bumped_provenance = {
        "role": {"value": "test", "basis": "simulated-classifier-v2"},
        "subject": {"value": "selected_repository", "basis": None},
        "derivation": {"status": "source"},
        "validity": {"declared_status": "unknown"},
        "classification": {
            "schema_version": "provenance-v1",
            "classifier_version": "simulated-v2",
            "scope": "artifact",
        },
    }
    from src.api.v1 import codebase_ingest as codebase_ingest_module
    from src.core.codebase import codebase_persistence as codebase_persistence_module

    # Both modules import classify_node independently (persist_graph's
    # DocumentNode-level recompute and codebase_ingest's chunk/reuse-path
    # recompute are separate call sites by design -- see B1/B2) -- patch
    # both so this test simulates one consistent classifier-version bump
    # across the whole pipeline, not a contradiction between the two.
    monkeypatch.setattr(
        codebase_ingest_module, "classify_node", lambda *a, **k: bumped_provenance
    )
    monkeypatch.setattr(
        codebase_persistence_module, "classify_node", lambda *a, **k: bumped_provenance
    )

    id2 = uuid.uuid4()
    embedder, embedded_ids = _counting_embedder()
    _run_ingestion(
        monkeypatch, vector_http_url, tmp_path, repo_id, id2, embedder=embedder,
    )

    # No re-embed for the reused artifact -- the fix must not have
    # started re-chunking/re-embedding to refresh provenance.
    assert "keep.py" not in embedded_ids and "keep.py#keep" not in embedded_ids

    # DocumentNode.provenance (Stage B1) was always going to pick this up
    # (persist_graph recomputes on every upsert) -- confirmed as a sanity
    # baseline, not the regression this test targets.
    Session = get_sessionmaker()
    with Session() as s:
        keep_node = s.get(DocumentNode, keep_doc_id)
        assert keep_node.provenance == bumped_provenance

    refreshed_metadata = _vector_source_metadata(keep_doc_id)
    assert refreshed_metadata, "reused rows must still exist (no delete/re-insert)"
    for row in refreshed_metadata:
        assert row["provenance"] == bumped_provenance, (
            "reused vector row's source_metadata.provenance must be "
            "refreshed to the current classifier's output without a "
            "re-embed"
        )
        # Every other source_metadata key survives the patch untouched.
        assert row["canonical_id"] == original_canonical_id


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
# CI-06 (#337): vectors built under the legacy embedding-input contract
# (heuristic-v1 chunks cut to 800 chars by the embedder) are never reused.
# ---------------------------------------------------------------------

def test_legacy_input_contract_generation_is_fully_reembedded(
    monkeypatch, vector_http_url, repo_id, tmp_path,
):
    _write_repo(tmp_path, "def touch():\n    return 1\n")

    id1 = uuid.uuid4()
    _run_ingestion(monkeypatch, vector_http_url, tmp_path, repo_id, id1)
    req1 = _request_row(id1)
    assert req1.chunking_config_version == api.ChunkerFactory.VERSION
    assert req1.embedding_config_version.endswith(f":{api.EMBEDDING_INPUT_CONTRACT}")

    # Make generation 1 look exactly like one built before CI-06.
    _mark_legacy_contract(id1)

    id2 = uuid.uuid4()
    embedder, embedded_ids = _counting_embedder()
    _run_ingestion(
        monkeypatch, vector_http_url, tmp_path, repo_id, id2, embedder=embedder,
    )
    req2 = _request_row(id2)
    assert req2.status == "completed" and req2.is_incremental is True
    assert "keep.py" in embedded_ids and "touch.py" in embedded_ids, (
        "unchanged files built under the legacy contract must be re-embedded"
    )
    # Fresh vectors exist for generation 2 (superseded-generation cleanup is
    # best-effort and not under test here).
    keep_doc_id = _document_id(repo_id, "keep.py")
    assert str(id2) in _vector_ingestion_ids(keep_doc_id)

    # Generation 2 is current-contract: an unchanged re-run reuses it again.
    id3 = uuid.uuid4()
    embedder, embedded_ids = _counting_embedder()
    _run_ingestion(
        monkeypatch, vector_http_url, tmp_path, repo_id, id3, embedder=embedder,
    )
    assert "keep.py" not in embedded_ids and "touch.py" not in embedded_ids


def _vector_generations(document_id):
    """Ingestion id of every vector row for a document, one entry per row."""
    Session = get_sessionmaker()
    with Session() as s:
        rows = s.execute(
            text(
                "SELECT ingestion_id FROM ingestion_service.vector_chunks "
                "WHERE document_id = :document_id"
            ),
            {"document_id": document_id},
        ).all()
        return sorted(str(r[0]) for r in rows)


def _mark_legacy_contract(ingestion_id):
    Session = get_sessionmaker()
    with Session() as s:
        row = s.get(IngestionRequest, ingestion_id)
        settings = api.get_settings()
        row.chunking_config_version = "heuristic-v1"
        # The deployed pre-CI-06 identity: provider and model only.
        row.embedding_config_version = (
            f"{settings.EMBEDDING_PROVIDER}:{settings.OLLAMA_EMBED_MODEL}"
        )
        s.commit()


def _fail_superseded_cleanup(monkeypatch):
    def fail(*args, **kwargs):
        raise RuntimeError("injected superseded-generation cleanup failure")

    monkeypatch.setattr(api.db_utils, "superseded_ingestion_ids_for_repo", fail)


def test_failed_cleanup_never_mixes_generations_on_reuse(
    monkeypatch, vector_http_url, repo_id, tmp_path,
):
    """CI-06 review R2 (#337), with one embedding contract throughout:
    G1 fresh -> G2 re-embeds a changed file while cleanup of G1 fails ->
    G3 reuses that file unchanged. Only G2's rows may become G3's rows; the
    stale G1 rows (obsolete source text) must stay G1 and remain removable."""
    _write_repo(tmp_path, "def touch():\n    return 1\n")
    _fail_superseded_cleanup(monkeypatch)

    id1 = uuid.uuid4()
    _run_ingestion(monkeypatch, vector_http_url, tmp_path, repo_id, id1)
    touch_doc_id = _document_id(repo_id, "touch.py")
    stale_rows = _vector_generations(touch_doc_id)
    assert stale_rows and set(stale_rows) == {str(id1)}

    # G2: touch.py changes, so it is re-embedded under the same document_id.
    (tmp_path / "touch.py").write_text(
        "def touch():\n    return 2\n", encoding="utf-8"
    )
    id2 = uuid.uuid4()
    _run_ingestion(monkeypatch, vector_http_url, tmp_path, repo_id, id2)
    assert _request_row(id2).status == "completed"
    assert _document_id(repo_id, "touch.py") == touch_doc_id
    after_g2 = _vector_generations(touch_doc_id)
    # Cleanup failed, so G1's obsolete rows coexist with G2's for one document.
    assert after_g2.count(str(id1)) == len(stale_rows)
    current_rows = after_g2.count(str(id2))
    assert current_rows > 0

    # G3: nothing changes; touch.py is reused from G2.
    id3 = uuid.uuid4()
    embedder, embedded_ids = _counting_embedder()
    _run_ingestion(
        monkeypatch, vector_http_url, tmp_path, repo_id, id3, embedder=embedder,
    )
    req3 = _request_row(id3)
    assert req3.status == "completed" and req3.is_incremental is True
    assert "touch.py" not in embedded_ids and "touch.py#touch" not in embedded_ids

    after_g3 = _vector_generations(touch_doc_id)
    assert after_g3.count(str(id3)) == current_rows, (
        "only the expected prior generation's rows may join the new generation"
    )
    assert after_g3.count(str(id1)) == len(stale_rows), "stale rows were relabeled"
    assert str(id2) not in after_g3

    # Generation-scoped deletion of G1 now removes exactly the stale rows.
    HttpVectorStore(vector_http_url).delete_by_ingestion_id(str(id1))
    assert _vector_generations(touch_doc_id) == [str(id3)] * current_rows


def test_reusable_artifact_without_prior_vectors_is_embedded(
    monkeypatch, vector_http_url, repo_id, tmp_path,
):
    """Reuse is verified: an unchanged-file artifact with no vectors in the
    prior generation is embedded instead of completing without vectors."""
    _write_repo(tmp_path, "def touch():\n    return 1\n")

    id1 = uuid.uuid4()
    _run_ingestion(monkeypatch, vector_http_url, tmp_path, repo_id, id1)
    keep_doc_id = _document_id(repo_id, "keep.py")
    Session = get_sessionmaker()
    with Session() as s:
        s.execute(
            text(
                "DELETE FROM ingestion_service.vector_chunks "
                "WHERE document_id = :document_id"
            ),
            {"document_id": keep_doc_id},
        )
        s.commit()

    id2 = uuid.uuid4()
    embedder, embedded_ids = _counting_embedder()
    _run_ingestion(
        monkeypatch, vector_http_url, tmp_path, repo_id, id2, embedder=embedder,
    )
    req2 = _request_row(id2)
    assert req2.status == "completed" and req2.is_incremental is True
    assert "keep.py" in embedded_ids
    assert set(_vector_generations(keep_doc_id)) == {str(id2)}


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


# ---------------------------------------------------------------------
# Issue #416 WP4: a reused artifact gains window ranges without a re-embed.
# Vectors written before window ranges existed are simulated by stripping the
# range keys after the first generation. The reuse path must patch them back,
# digest-verified, leaving text, vectors and ordinals exactly as they were.
# ---------------------------------------------------------------------

LEGACY_REASON = "line span not persisted at ingestion"
LOCATION_KEYS = ("start_line", "end_line", "range_reason")


def _keep_document_ids(repo_id):
    return [
        _document_id(repo_id, "keep.py"),
        _document_id(repo_id, "keep.py#keep"),
    ]


def _vector_rows(document_id):
    Session = get_sessionmaker()
    with Session() as s:
        rows = s.execute(
            text(
                "SELECT chunk_index, chunk_text, vector::text, chunk_id, "
                "ingestion_id::text, source_metadata FROM "
                "ingestion_service.vector_chunks WHERE document_id = :d "
                "ORDER BY chunk_index"
            ),
            {"d": document_id},
        ).all()
        return [tuple(r) for r in rows]


def _make_legacy(document_ids):
    """Rewrite the stored location metadata as a pre-#416 vector had it."""
    Session = get_sessionmaker()
    with Session() as s:
        s.execute(
            text(
                "UPDATE ingestion_service.vector_chunks SET source_metadata = "
                "(source_metadata - 'start_line' - 'end_line' - 'range_reason') "
                "|| CAST(:legacy AS jsonb) WHERE document_id = ANY(:ids)"
            ),
            {"legacy": '{"range_reason": "%s"}' % LEGACY_REASON,
             "ids": list(document_ids)},
        )
        s.commit()


def _without_location(metadata):
    return {k: v for k, v in metadata.items() if k not in LOCATION_KEYS}


def test_reuse_attaches_ranges_to_legacy_vectors_without_reembed(
    monkeypatch, vector_http_url, repo_id, tmp_path,
):
    _write_repo(tmp_path, "def touch():\n    return 1\n")
    id1 = uuid.uuid4()
    _run_ingestion(monkeypatch, vector_http_url, tmp_path, repo_id, id1)

    docs = _keep_document_ids(repo_id)
    first = {d: _vector_rows(d) for d in docs}
    assert all(first[d] for d in docs)
    # The first generation already tags windows with ranges (WP2).
    original = {
        d: [(r[5].get("start_line"), r[5].get("end_line")) for r in first[d]]
        for d in docs
    }
    assert all(a is not None for d in docs for a, _ in original[d])
    _make_legacy(docs)
    assert all(
        "start_line" not in r[5] and r[5]["range_reason"] == LEGACY_REASON
        for d in docs for r in _vector_rows(d)
    )

    (tmp_path / "touch.py").write_text("def touch():\n    return 2\n", encoding="utf-8")
    id2 = uuid.uuid4()
    embedder, embedded_ids = _counting_embedder()
    _run_ingestion(
        monkeypatch, vector_http_url, tmp_path, repo_id, id2, embedder=embedder,
    )

    assert "keep.py" not in embedded_ids and "keep.py#keep" not in embedded_ids
    # The run's final result says the ranges were patched, not just reused.
    progress = _request_row(id2).ingestion_metadata["embed_progress"]
    assert progress["ranges_outcome"] == "patched"
    assert progress["ranges_patched"] == progress["ranges_requested"] > 0
    assert progress["ranges_skipped"] == 0 and progress["ranges_retried_batches"] == 0
    for d in docs:
        after = _vector_rows(d)
        assert len(after) == len(first[d])
        for old, new in zip(first[d], after):
            # Text, ordinal, chunk id and vector are exactly what they were.
            assert (old[0], old[1], old[2], old[3]) == (new[0], new[1], new[2], new[3])
            assert new[4] == str(id2)  # moved to the new generation
            assert _without_location(new[5]) == _without_location(old[5])
        assert [(r[5].get("start_line"), r[5].get("end_line")) for r in after] == (
            original[d]
        )
        assert all("range_reason" not in r[5] for r in after)


def test_reuse_skips_a_passage_whose_digest_does_not_match(
    monkeypatch, vector_http_url, repo_id, tmp_path,
):
    _write_repo(tmp_path, "def touch():\n    return 1\n")
    id1 = uuid.uuid4()
    _run_ingestion(monkeypatch, vector_http_url, tmp_path, repo_id, id1)

    module_doc, function_doc = _keep_document_ids(repo_id)
    _make_legacy([module_doc, function_doc])
    Session = get_sessionmaker()
    # The stored passage is no longer the window ingestion recomputes.
    with Session() as s:
        s.execute(
            text(
                "UPDATE ingestion_service.vector_chunks SET chunk_text = 'tampered' "
                "WHERE document_id = :d"
            ),
            {"d": module_doc},
        )
        s.commit()
    tampered_before = _vector_rows(module_doc)

    (tmp_path / "touch.py").write_text("def touch():\n    return 2\n", encoding="utf-8")
    id2 = uuid.uuid4()
    _run_ingestion(monkeypatch, vector_http_url, tmp_path, repo_id, id2)
    assert _request_row(id2).status == "completed"
    # Reuse succeeded, but the result says the patching was only partial.
    progress = _request_row(id2).ingestion_metadata["embed_progress"]
    assert progress["ranges_outcome"] == "partial"
    assert progress["ranges_skipped"] >= 1
    assert progress["ranges_patched"] + progress["ranges_skipped"] == (
        progress["ranges_requested"]
    )

    # The mismatched passage was still reused (moved), but its metadata and text
    # are exactly as they were: no range was attached to a passage that is not
    # the window the range was computed for.
    tampered_after = _vector_rows(module_doc)
    assert len(tampered_after) == len(tampered_before)
    for old, new in zip(tampered_before, tampered_after):
        assert (old[0], old[1], old[2], old[3], old[5]) == (
            new[0], new[1], new[2], new[3], new[5])
        assert new[4] == str(id2)
    # The other artifact in the same ingestion was patched.
    assert all(r[5].get("start_line") for r in _vector_rows(function_doc))


# ---------------------------------------------------------------------
# Issue #416 live finding: a failure between retag requests must not leave a
# partially promoted generation eligible for serving. Each retag request is
# atomic in the vector store, but a run is many requests; the generation is
# promoted only when the whole run is marked `completed`. A run that dies
# midway is `failed`, nothing is served from it, and the next run is a full
# ingestion (its prior generation did not complete), which leaves one
# consistent generation with no duplicated vectors.
# ---------------------------------------------------------------------

def test_failure_between_retag_requests_is_never_servable_and_recovers_by_full_run(
    monkeypatch, vector_http_url, repo_id, tmp_path,
):
    from src.core import db_utils

    _write_repo(tmp_path, "def touch():\n    return 1\n")
    id1 = uuid.uuid4()
    _run_ingestion(monkeypatch, vector_http_url, tmp_path, repo_id, id1)
    docs = _keep_document_ids(repo_id)
    first_counts = {d: len(_vector_rows(d)) for d in docs}
    assert db_utils.resolve_current_generation(repo_id) == str(id1)

    (tmp_path / "touch.py").write_text("def touch():\n    return 2\n", encoding="utf-8")
    original = HttpVectorStore._post_retag
    calls = {"n": 0}

    def times_out_on_the_second_request(self, *args, **kwargs):
        calls["n"] += 1
        if calls["n"] == 2:
            raise requests.Timeout("read timed out")
        return original(self, *args, **kwargs)

    monkeypatch.setattr(HttpVectorStore, "RETAG_BATCH_SIZE", 1)  # one doc per request
    monkeypatch.setattr(HttpVectorStore, "_post_retag", times_out_on_the_second_request)
    id2 = uuid.uuid4()
    _run_ingestion(monkeypatch, vector_http_url, tmp_path, repo_id, id2)

    # The first request committed, the second did not: a split generation exists
    # physically, and it must not be servable.
    assert calls["n"] == 2
    assert _request_row(id2).status == "failed"
    generations = {g for d in docs for g in _vector_ingestion_ids(d)}
    assert generations == {str(id1), str(id2)}, (
        f"generations on the reused documents: {sorted(generations)}; "
        f"id1={id1} id2={id2}; per document: "
        f"{ {d: sorted(_vector_ingestion_ids(d)) for d in docs} }"
    )
    assert db_utils.resolve_current_generation(repo_id) is None
    assert db_utils.generation_status(repo_id) == "failed"

    # Recovery: the next run sees no completed prior generation, so it is a full
    # ingestion, and ends with one consistent generation and no duplicates.
    monkeypatch.setattr(HttpVectorStore, "_post_retag", original)
    id3 = uuid.uuid4()
    _run_ingestion(monkeypatch, vector_http_url, tmp_path, repo_id, id3)
    assert _request_row(id3).status == "completed"
    assert _request_row(id3).is_incremental is False
    assert db_utils.resolve_current_generation(repo_id) == str(id3)
    # Rows of older generations may linger here: their best-effort cleanup call
    # needs the production service hostname, which this test process cannot
    # resolve. They are not served; what matters is the current generation.
    for d in docs:
        current = [r for r in _vector_rows(d) if r[4] == str(id3)]
        assert len(current) == first_counts[d]
        assert len({r[0] for r in current}) == len(current)  # no duplicate ordinals
