# tests/core/vectorstore/test_ann_index_usage.py
"""
F-10 (WP-S4) + WP-S4B: vector search must be index-backed, not a
sequential scan.

Asserts via EXPLAIN against the docker-compose.test.yml Postgres
(migrations 20260718_vc_idx + 20260719_typed_cols applied) that:
- ANN ordering uses the HNSW index (ix_vector_chunks_hnsw);
- doc_type / repo_id filters use the typed-column indexes (WP-S4B
  replaced the JSONB expression indexes);
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
                    "repo_id": f"repo-{i % 3}",
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
    """WP-S4B: the hybrid query's exact filter shape (repo_id + doc_type)
    is served by typed-column indexes — the planner may pick the
    composite or a single-column index depending on stats, but it must
    not fall back to a seq scan or JSONB evaluation."""
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
    ), plan
    assert "Seq Scan" not in plan, plan
    assert "source_metadata" not in plan, plan


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
