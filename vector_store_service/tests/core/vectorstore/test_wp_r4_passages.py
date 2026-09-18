"""WP-R4 exact scoped passage selection against real PostgreSQL/pgvector."""
import os
import uuid

import pytest
import psycopg
from shared.models.vector import VectorMetadata, VectorRecord
from src.core.vectorstore.pgvector_store import PgVectorStore

pytestmark = [pytest.mark.integration, pytest.mark.docker]


def test_query_selects_tail_with_generation_and_repository_isolation():
    dsn = os.environ.get("DATABASE_URL", "")
    if not dsn:
        pytest.skip("DATABASE_URL not set")
    store = PgVectorStore(dsn, dimension=1024)
    generation, stale = str(uuid.uuid4()), str(uuid.uuid4())
    document = str(uuid.uuid4())
    repo = str(uuid.uuid4())
    query = [1.0] + [0.0] * 1023
    records = []
    for ordinal in range(100):
        records.append(VectorRecord(
            vector=query if ordinal == 97 else [0.0, 1.0] + [0.0] * 1022,
            metadata=VectorMetadata(
                ingestion_id=generation, chunk_id=f"{generation}-{ordinal}",
                chunk_index=ordinal, chunk_strategy="test", chunk_text=str(ordinal),
                document_id=document, source_metadata={"repo_id": repo},
            ),
        ))
    records.append(VectorRecord(vector=query, metadata=VectorMetadata(
        ingestion_id=stale, chunk_id=stale, chunk_index=0, chunk_strategy="test",
        chunk_text="stale", document_id=document, source_metadata={"repo_id": repo},
    )))
    with psycopg.connect(dsn) as conn:
        conn.execute(
            "INSERT INTO ingestion_service.ingestion_requests "
            "(ingestion_id, source_type, repo_id) VALUES (%s, 'test', %s)",
            (generation, repo),
        )
        conn.execute(
            "INSERT INTO ingestion_service.document_nodes "
            "(document_id, repo_id, canonical_id, relative_path, title, summary, "
            "source, ingestion_id, doc_type) "
            "VALUES (%s, %s, 'tail.py', 'tail.py', 'tail', '', 'test', %s, 'code')",
            (document, repo, generation),
        )
    try:
        store.add(records)
        hits = store.get_chunks_by_document_id(
            document, 3, query_vector=query, ingestion_id=generation, repo_id=repo,
        )
        assert [hit.metadata.chunk_index for hit in hits] == [97, 0, 1]
        assert all(str(hit.metadata.ingestion_id) == generation for hit in hits)
        assert hits[0].metadata.score == pytest.approx(1.0)
        assert store.get_chunks_by_document_id(
            document, 3, query_vector=query, ingestion_id=generation, repo_id="other",
        ) == []
        ordinal_hits = store.get_chunks_by_document_id(
            document, 3, ingestion_id=generation, repo_id=repo,
        )
        assert [hit.metadata.chunk_index for hit in ordinal_hits] == [0, 1, 2]
        seeds = store.similarity_search(query, 3, {
            "repo_id": repo, "ingestion_id": generation,
        })
        assert all(str(hit.metadata.ingestion_id) == generation for hit in seeds)
        assert [hit.metadata.score for hit in seeds] == sorted(
            (hit.metadata.score for hit in seeds), reverse=True,
        )
    finally:
        store.delete_by_ingestion_id(generation)
        store.delete_by_ingestion_id(stale)
        with psycopg.connect(dsn) as conn:
            conn.execute(
                "DELETE FROM ingestion_service.document_nodes WHERE document_id = %s",
                (document,),
            )
            conn.execute(
                "DELETE FROM ingestion_service.ingestion_requests "
                "WHERE ingestion_id = %s", (generation,),
            )
