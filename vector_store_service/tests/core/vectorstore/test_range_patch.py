"""Issue #416 WP3 (specs/015-per-window-source-ranges): the source-range patch
carried by the retag request, against real PostgreSQL/pgvector.

Requirements checked here:
1. only a row whose artifact and passage digest match is patched;
2. the row must belong to the expected prior generation;
3. only start_line, end_line and range_reason may change;
4. vector, passage text, ordinal and every other metadata key are untouched;
5. a rejected or failed update leaves the stored record exactly as it was;
6. both successful reuse and each rejection path are covered.
"""
import hashlib
import os
import uuid

import psycopg
import pytest
from shared.models.vector import VectorMetadata, VectorRecord
from src.core.vectorstore.pgvector_store import PgVectorStore

pytestmark = [pytest.mark.integration, pytest.mark.docker]


def sha(text):
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def ok(index, text, start, end):
    return {"chunk_index": index, "text_sha256": sha(text), "start_line": start,
            "end_line": end, "range_reason": None}


def null(index, text, reason):
    return {"chunk_index": index, "text_sha256": sha(text), "start_line": None,
            "end_line": None, "range_reason": reason}


def record(generation, document, ordinal, text, repo, extra=None):
    meta = {"repo_id": repo, "provenance": {"v": "keep"}, "start_line": 1,
            "end_line": 1, "range_reason": "stale"}
    meta.update(extra or {})
    return VectorRecord(
        vector=[float(ordinal + 1)] + [0.0] * 1023,
        metadata=VectorMetadata(
            ingestion_id=generation, chunk_id=str(uuid.uuid4()),
            chunk_index=ordinal, chunk_strategy="test", chunk_text=text,
            document_id=document, source_metadata=meta,
        ),
    )


class Env:
    """A tiny repository: two generations, two documents, three passages."""

    def __init__(self):
        dsn = os.environ.get("DATABASE_URL", "")
        if not dsn:
            pytest.skip("DATABASE_URL not set")
        self.dsn = dsn
        self.store = PgVectorStore(dsn, dimension=1024)
        self.repo = str(uuid.uuid4())
        self.g_old, self.g_new = str(uuid.uuid4()), str(uuid.uuid4())
        self.doc_a, self.doc_b = str(uuid.uuid4()), str(uuid.uuid4())
        self.texts = {(self.doc_a, 0): "alpha-0", (self.doc_a, 1): "alpha-1",
                      (self.doc_b, 0): "beta-0"}
        with psycopg.connect(dsn) as conn:
            for generation in (self.g_old, self.g_new):
                conn.execute(
                    "INSERT INTO ingestion_service.ingestion_requests "
                    "(ingestion_id, source_type, repo_id) VALUES (%s, 'test', %s)",
                    (generation, self.repo),
                )
            for document, name in ((self.doc_a, "a"), (self.doc_b, "b")):
                conn.execute(
                    "INSERT INTO ingestion_service.document_nodes "
                    "(document_id, repo_id, canonical_id, relative_path, title, "
                    "summary, source, ingestion_id, doc_type) "
                    "VALUES (%s, %s, %s, %s, 't', '', 'test', %s, 'code')",
                    (document, self.repo, f"{name}.py", f"{name}.py", self.g_new),
                )
        self.store.add([
            record(self.g_old, doc, idx, text, self.repo)
            for (doc, idx), text in self.texts.items()
        ])

    def snapshot(self):
        """Everything stored for the repository's passages, byte for byte."""
        with psycopg.connect(self.dsn) as conn:
            return conn.execute(
                "SELECT document_id::text, chunk_index, ingestion_id::text, chunk_id, "
                "chunk_text, vector::text, provider, source_metadata::text "
                "FROM ingestion_service.vector_chunks "
                "WHERE document_id IN (%s, %s) ORDER BY document_id, chunk_index",
                (self.doc_a, self.doc_b),
            ).fetchall()

    def meta(self, document, index):
        with psycopg.connect(self.dsn) as conn:
            return conn.execute(
                "SELECT ingestion_id::text, source_metadata FROM "
                "ingestion_service.vector_chunks "
                "WHERE document_id = %s AND chunk_index = %s",
                (document, index),
            ).fetchone()

    def close(self):
        for generation in (self.g_old, self.g_new):
            self.store.delete_by_ingestion_id(generation)
        with psycopg.connect(self.dsn) as conn:
            conn.execute(
                "DELETE FROM ingestion_service.document_nodes WHERE repo_id = %s",
                (self.repo,),
            )
            conn.execute(
                "DELETE FROM ingestion_service.ingestion_requests WHERE repo_id = %s",
                (self.repo,),
            )

    def retag(self, ranges, expected=None, **kw):
        return self.store.retag_ingestion_id(
            [self.doc_a, self.doc_b], self.g_new, None,
            expected_ingestion_id=expected or self.g_old,
            source_ranges_by_document_id=ranges, **kw,
        )


@pytest.fixture
def env():
    e = Env()
    try:
        yield e
    finally:
        e.close()


def all_ranges(env):
    return {
        env.doc_a: [ok(0, "alpha-0", 10, 12), null(1, "alpha-1", "no offset")],
        env.doc_b: [ok(0, "beta-0", 3, 3)],
    }


def test_success_moves_rows_and_patches_only_the_location_keys(env):
    before = env.snapshot()
    result = env.retag(all_ranges(env))

    assert result.rows == 3 and result.ranges_patched == 3
    assert list(result.ranges_skipped) == []
    gen, meta = env.meta(env.doc_a, 0)
    assert gen == env.g_new
    assert (meta["start_line"], meta["end_line"]) == (10, 12)
    assert "range_reason" not in meta  # a range carries no reason
    gen, meta = env.meta(env.doc_a, 1)
    assert "start_line" not in meta and meta["range_reason"] == "no offset"
    # Everything else is byte for byte what it was; only generation and the
    # three location keys differ.
    after = env.snapshot()
    assert len(before) == len(after) == 3
    import json
    for old, new in zip(before, after):
        assert old[:2] == new[:2]  # document, ordinal
        assert old[3:7] == new[3:7]  # chunk_id, text, vector, provider
        assert new[2] == env.g_new and old[2] == env.g_old
        old_meta, new_meta = json.loads(old[7]), json.loads(new[7])
        for key in ("start_line", "end_line", "range_reason"):
            old_meta.pop(key, None)
            new_meta.pop(key, None)
        assert old_meta == new_meta  # repo_id, provenance, ... preserved


def test_digest_mismatch_leaves_that_row_untouched_and_is_reported(env):
    ranges = all_ranges(env)
    ranges[env.doc_a][0] = ok(0, "NOT the stored text", 10, 12)
    before = {(r[0], r[1]): r for r in env.snapshot()}
    result = env.retag(ranges)

    assert result.ranges_patched == 2
    assert [(s["document_id"], s["chunk_index"], s["reason"])
            for s in result.ranges_skipped] == [
        (env.doc_a, 0, "digest mismatch")]
    after = {(r[0], r[1]): r for r in env.snapshot()}
    skipped = after[(env.doc_a, 0)]
    # The artifact moved to the new generation but this passage's metadata is
    # exactly as it was.
    assert skipped[2] == env.g_new
    assert skipped[3:] == before[(env.doc_a, 0)][3:]
    # The rest of the batch still applied.
    assert env.meta(env.doc_b, 0)[1]["start_line"] == 3


def test_stale_generation_changes_nothing(env):
    before = env.snapshot()
    result = env.retag(all_ranges(env), expected=str(uuid.uuid4()))
    assert result.rows == 0 and result.ranges_patched == 0
    assert len(result.ranges_skipped) == 3
    assert {s["reason"] for s in result.ranges_skipped} == {
        "row not found at this generation"}
    assert env.snapshot() == before


def test_unknown_document_or_chunk_is_reported_and_writes_nothing(env):
    ranges = all_ranges(env)
    ranges[env.doc_a].append(ok(9, "never stored", 1, 2))
    before = env.snapshot()
    result = env.retag(ranges)
    assert result.ranges_patched == 3
    assert [(s["document_id"], s["chunk_index"]) for s in result.ranges_skipped] == [
        (env.doc_a, 9)]
    assert len(env.snapshot()) == len(before)


def test_failure_after_some_rows_rolls_everything_back(env, monkeypatch):
    """Injects a failure on the second batch: the first batch's patches and the
    retag itself must not survive. No row is half-transitioned."""
    env.store.RANGE_PATCH_BATCH = 1
    original = PgVectorStore._patch_range_batch
    calls = {"n": 0}

    def flaky(self, cur, new_generation, batch):
        calls["n"] += 1
        if calls["n"] == 2:
            raise RuntimeError("injected failure")
        return original(self, cur, new_generation, batch)

    monkeypatch.setattr(PgVectorStore, "_patch_range_batch", flaky)
    before = env.snapshot()
    with pytest.raises(RuntimeError, match="injected failure"):
        env.retag(all_ranges(env))
    assert calls["n"] == 2  # the first batch really ran before the failure
    assert env.snapshot() == before  # generation, metadata, text, vector: all as before


def test_malformed_request_is_refused_before_any_write(env):
    before = env.snapshot()
    bad = {env.doc_a: [{**ok(0, "alpha-0", 10, 12), "text_sha256": "nope"}]}
    with pytest.raises(ValueError):
        env.retag(bad)
    assert env.snapshot() == before


def test_a_retag_without_ranges_is_exactly_the_old_behavior(env):
    result = env.store.retag_ingestion_id(
        [env.doc_a, env.doc_b], env.g_new, None, expected_ingestion_id=env.g_old
    )
    assert result.rows == 3 and result.ranges_patched == 0
    gen, meta = env.meta(env.doc_a, 0)
    assert gen == env.g_new
    assert (meta["start_line"], meta["end_line"]) == (1, 1)  # untouched seed values
    assert meta["range_reason"] == "stale"


def test_batches_are_applied_across_a_batch_boundary(env):
    env.store.RANGE_PATCH_BATCH = 1
    result = env.retag(all_ranges(env))
    assert result.ranges_patched == 3
    assert env.meta(env.doc_b, 0)[1]["start_line"] == 3
