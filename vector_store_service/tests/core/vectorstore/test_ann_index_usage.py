# tests/core/vectorstore/test_ann_index_usage.py
"""
F-10 (WP-S4) + WP-S4B: vector search must be index-backed, not a
sequential scan.

Asserts via EXPLAIN against the docker-compose.test.yml Postgres
(migrations 20260718_vc_idx + 20260719_typed_cols + 20260829_src_type
applied) that:
- ANN ordering uses the HNSW index (ix_vector_chunks_hnsw);
- doc_type / repo_id / source_type filters use the typed-column indexes
  (WP-S4B, extended by issue #64 — replaced the JSONB expression indexes);
- document_id lookups use their btree index.

The test dataset is tiny, so the planner would prefer a seq scan on
cost; enable_seqscan is disabled per-transaction to prove the indexes
are *usable* for these exact query shapes (wrong operator class or a
non-matching expression would still fall back to seq scan).

Run with DATABASE_URL pointing at the test DB (localhost:5433).
"""
import json
import os
import random
import uuid

import psycopg
import pytest

from src.core.vectorstore.pgvector_store import PgVectorStore
from shared.models.vector import VectorRecord, VectorMetadata

pytestmark = [pytest.mark.integration, pytest.mark.docker]

DIM = 1024


def _dsn():
    url = os.environ.get("DATABASE_URL", "")
    if not url:
        pytest.skip("DATABASE_URL not set")
    return url


@pytest.fixture(scope="module")
def store():
    dsn = _dsn()
    store = PgVectorStore(dsn=dsn, dimension=DIM, provider="mock")
    ingestion_id = str(uuid.uuid4())
    rng = random.Random(42)
    records = [
        VectorRecord(
            vector=[rng.uniform(-1, 1) for _ in range(DIM)],
            metadata=VectorMetadata(
                ingestion_id=ingestion_id,
                chunk_id=f"chunk-{i}",
                chunk_index=i,
                chunk_strategy="test",
                chunk_text=f"text {i}",
                source_metadata={
                    "doc_type": "code" if i % 2 == 0 else "file",
                    "source_type": "code" if i % 2 == 0 else "file",
                    "repo_id": f"repo-{i % 3}",
                    # WP-L6a: only "code" rows carry a language, mirroring
                    # real ingestion (docs/external nodes carry none).
                    **(
                        {"language": "python" if i % 4 == 0 else "typescript"}
                        if i % 2 == 0 else {}
                    ),
                },
                provider="mock",
            ),
        )
        for i in range(60)
    ]
    store.add(records)
    yield store
    store.delete_by_ingestion_id(ingestion_id)


def _explain(query, params=()):
    with psycopg.connect(_dsn()) as conn:
        with conn.cursor() as cur:
            cur.execute("SET LOCAL enable_seqscan = off")
            cur.execute("EXPLAIN (FORMAT JSON) " + query, params)
            return json.dumps(cur.fetchone()[0])


def test_similarity_search_uses_hnsw_index(store):
    qvec = "[" + ",".join(["0.1"] * DIM) + "]"
    plan = _explain(
        f"""
        SELECT chunk_id FROM ingestion_service.vector_chunks
        ORDER BY vector <=> '{qvec}'::vector
        LIMIT 5
        """
    )
    assert "ix_vector_chunks_hnsw" in plan, plan
    assert "Seq Scan" not in plan, plan


def test_doc_type_filter_uses_typed_column_index(store):
    plan = _explain(
        """
        SELECT chunk_id FROM ingestion_service.vector_chunks
        WHERE doc_type = %s
        """,
        ("code",),
    )
    assert "ix_vector_chunks_doc_type_col" in plan, plan


def test_repo_filter_uses_typed_column_indexes(store):
    """WP-S4B: the hybrid query's original filter shape (repo_id + doc_type)
    is served by typed-column indexes — the planner may pick any index
    with repo_id or doc_type as a column (composite or single-column,
    including issue #64's (repo_id, source_type) index and WP-L6a's
    (repo_id, language) index, both of which also serve repo_id-only
    lookups) depending on stats, but it must not fall back to a seq scan
    or JSONB evaluation."""
    plan = _explain(
        """
        SELECT chunk_id FROM ingestion_service.vector_chunks
        WHERE repo_id = %s AND doc_type = %s
        """,
        ("repo-1", "code"),
    )
    assert (
        "ix_vector_chunks_repo_doc" in plan
        or "ix_vector_chunks_doc_type_col" in plan
        or "ix_vector_chunks_repo_source_type" in plan
        or "ix_vector_chunks_repo_language" in plan
    ), plan
    assert "Seq Scan" not in plan, plan
    assert "source_metadata" not in plan, plan


def test_source_type_filter_uses_typed_column_index(store):
    """Issue #64: source_type is the marker hybrid_retrieve() actually
    filters on — must be index-backed, not a JSONB scan."""
    plan = _explain(
        """
        SELECT chunk_id FROM ingestion_service.vector_chunks
        WHERE source_type = %s
        """,
        ("code",),
    )
    assert "ix_vector_chunks_source_type_col" in plan, plan


def test_repo_source_type_filter_uses_typed_column_indexes(store):
    """Issue #64: hybrid_retrieve()'s actual filter shape (repo_id +
    source_type) is index-backed — this is the query that used to
    silently fall back to an unfiltered repo-scoped search because the
    old repo_id + doc_type="code" shape never matched any row. The
    planner may pick any index with repo_id or source_type as a column
    (including the pre-existing (repo_id, doc_type) index and WP-L6a's
    (repo_id, language) index, both of which also serve repo_id-only
    lookups) — the point is no seq scan / JSONB evaluation, not a
    specific index name."""
    plan = _explain(
        """
        SELECT chunk_id FROM ingestion_service.vector_chunks
        WHERE repo_id = %s AND source_type = %s
        """,
        ("repo-1", "code"),
    )
    assert (
        "ix_vector_chunks_repo_source_type" in plan
        or "ix_vector_chunks_source_type_col" in plan
        or "ix_vector_chunks_repo_doc" in plan
        or "ix_vector_chunks_repo_language" in plan
    ), plan
    assert "Seq Scan" not in plan, plan
    assert "source_metadata" not in plan, plan


def test_language_filter_uses_typed_column_index(store):
    """WP-L6a (#85): language must be index-backed like doc_type/source_type."""
    plan = _explain(
        """
        SELECT chunk_id FROM ingestion_service.vector_chunks
        WHERE language = %s
        """,
        ("python",),
    )
    assert "ix_vector_chunks_language_col" in plan, plan


def test_repo_language_filter_uses_typed_column_indexes(store):
    """WP-L6a: /v1/rag's language-scoped filter shape (repo_id + language)
    is index-backed, not a seq scan or JSONB evaluation."""
    plan = _explain(
        """
        SELECT chunk_id FROM ingestion_service.vector_chunks
        WHERE repo_id = %s AND language = %s
        """,
        ("repo-1", "python"),
    )
    assert (
        "ix_vector_chunks_repo_language" in plan
        or "ix_vector_chunks_language_col" in plan
        or "ix_vector_chunks_repo_doc" in plan
        or "ix_vector_chunks_repo_source_type" in plan
    ), plan
    assert "Seq Scan" not in plan, plan
    assert "source_metadata" not in plan, plan


def test_language_scoped_search_returns_only_that_language(store):
    """SC-001: a language-scoped similarity_search never returns another
    language's rows."""
    rng = random.Random(13)
    results = store.similarity_search(
        [rng.uniform(-1, 1) for _ in range(DIM)],
        k=5,
        metadata_filter={
            "source_type": "code", "repo_id": "repo-1", "language": "python",
        },
    )
    assert len(results) > 0
    assert all(
        r.metadata.source_metadata.get("language") == "python" for r in results
    )


def test_typed_columns_backfilled_on_write(store):
    """store.add() populates the typed columns from source_metadata."""
    with psycopg.connect(_dsn()) as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT count(*) FROM ingestion_service.vector_chunks
                WHERE source_metadata->>'repo_id' IS NOT NULL
                  AND (repo_id IS NULL
                       OR repo_id != source_metadata->>'repo_id')
                """
            )
            assert cur.fetchone()[0] == 0
            cur.execute(
                """
                SELECT count(*) FROM ingestion_service.vector_chunks
                WHERE source_metadata->>'source_type' IS NOT NULL
                  AND (source_type IS NULL
                       OR source_type != source_metadata->>'source_type')
                """
            )
            assert cur.fetchone()[0] == 0
            cur.execute(
                """
                SELECT count(*) FROM ingestion_service.vector_chunks
                WHERE source_metadata->>'language' IS NOT NULL
                  AND (language IS NULL
                       OR language != source_metadata->>'language')
                """
            )
            assert cur.fetchone()[0] == 0


def test_document_id_lookup_uses_index(store):
    plan = _explain(
        """
        SELECT chunk_id FROM ingestion_service.vector_chunks
        WHERE document_id = %s
        """,
        (str(uuid.uuid4()),),
    )
    assert "ix_vector_chunks_document_id" in plan, plan


def test_similarity_search_end_to_end_with_ef_search(store):
    """The production query path (SET LOCAL hnsw.ef_search + search) works
    and returns ranked results."""
    rng = random.Random(7)
    results = store.similarity_search(
        [rng.uniform(-1, 1) for _ in range(DIM)],
        k=5,
        metadata_filter={"doc_type": "code"},
    )
    assert len(results) == 5
    scores = [r.metadata.score for r in results]
    assert scores == sorted(scores, reverse=True)
    assert all(
        r.metadata.source_metadata["doc_type"] == "code" for r in results
    )


def test_hybrid_retrieve_filter_shape_returns_results(store):
    """Issue #64: hybrid_retrieve()'s actual filter shape (repo_id +
    source_type="code") must return results, not silently fall back to
    an unfiltered search the way the old repo_id + doc_type="code"
    shape did (that value was never written by ingestion)."""
    rng = random.Random(11)
    results = store.similarity_search(
        [rng.uniform(-1, 1) for _ in range(DIM)],
        k=5,
        metadata_filter={"source_type": "code", "repo_id": "repo-1"},
    )
    assert len(results) > 0
    assert all(
        r.metadata.source_metadata["source_type"] == "code"
        and r.metadata.source_metadata["repo_id"] == "repo-1"
        for r in results
    )
