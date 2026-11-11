"""CI-06 review R2 (#337): retag is fenced to the reused prior generation.

Real PostgreSQL/pgvector. A reused document can still hold rows of an older
generation whose best-effort cleanup failed. Only the expected generation's
rows may become the new generation's rows, in both UPDATE branches.
"""
import os
import uuid

import psycopg
import pytest
from shared.models.vector import VectorMetadata, VectorRecord
from src.core.vectorstore.pgvector_store import PgVectorStore

pytestmark = [pytest.mark.integration, pytest.mark.docker]


def _record(generation, document, ordinal, text, repo):
    return VectorRecord(
        vector=[float(ordinal + 1)] + [0.0] * 1023,
        metadata=VectorMetadata(
            ingestion_id=generation, chunk_id=str(uuid.uuid4()),
            chunk_index=ordinal, chunk_strategy="test", chunk_text=text,
            document_id=document,
            source_metadata={"repo_id": repo, "provenance": {"v": "old"}},
        ),
    )


def _rows(dsn, document):
    with psycopg.connect(dsn) as conn:
        return sorted(
            (str(r[0]), r[1], r[2])
            for r in conn.execute(
                "SELECT ingestion_id, chunk_text, source_metadata->'provenance'->>'v' "
                "FROM ingestion_service.vector_chunks WHERE document_id = %s",
                (document,),
            ).fetchall()
        )


@pytest.mark.parametrize("with_provenance", [False, True])
def test_retag_moves_only_the_expected_generation(with_provenance):
    dsn = os.environ.get("DATABASE_URL", "")
    if not dsn:
        pytest.skip("DATABASE_URL not set")
    store = PgVectorStore(dsn, dimension=1024)
    repo = str(uuid.uuid4())
    g1, g2, g3 = (str(uuid.uuid4()) for _ in range(3))
    mixed, current_only, legacy_only = (str(uuid.uuid4()) for _ in range(3))

    with psycopg.connect(dsn) as conn:
        for generation in (g1, g2):
            conn.execute(
                "INSERT INTO ingestion_service.ingestion_requests "
                "(ingestion_id, source_type, repo_id) VALUES (%s, 'test', %s)",
                (generation, repo),
            )
        for document, name in ((mixed, "m"), (current_only, "c"), (legacy_only, "l")):
            conn.execute(
                "INSERT INTO ingestion_service.document_nodes "
                "(document_id, repo_id, canonical_id, relative_path, title, summary, "
                "source, ingestion_id, doc_type) "
                "VALUES (%s, %s, %s, %s, 't', '', 'test', %s, 'code')",
                (document, repo, f"{name}.py", f"{name}.py", g2),
            )
    try:
        store.add([
            # G1: legacy-contract rows whose cleanup "failed".
            _record(g1, mixed, 0, "legacy-0", repo),
            _record(g1, mixed, 1, "legacy-1", repo),
            _record(g1, legacy_only, 0, "legacy-only", repo),
            # G2: the current generation's rows, the ones reuse must carry.
            _record(g2, mixed, 0, "current-0", repo),
            _record(g2, current_only, 0, "current-only", repo),
        ])
        documents = [mixed, current_only, legacy_only]
        provenance = (
            {d: {"v": "new"} for d in documents} if with_provenance else None
        )

        result = store.retag_ingestion_id(
            documents, g3, provenance, expected_ingestion_id=g2
        )

        assert result.count == 2
        assert result.document_ids == sorted([mixed, current_only])
        refreshed = "new" if with_provenance else "old"
        assert _rows(dsn, mixed) == sorted([
            (g1, "legacy-0", "old"),
            (g1, "legacy-1", "old"),
            (g3, "current-0", refreshed),
        ])
        assert _rows(dsn, current_only) == [(g3, "current-only", refreshed)]
        assert _rows(dsn, legacy_only) == [(g1, "legacy-only", "old")]

        # Later cleanup of G1 removes exactly the stale rows; G3 is intact.
        store.delete_by_ingestion_id(g1)
        assert _rows(dsn, mixed) == [(g3, "current-0", refreshed)]
    finally:
        for generation in (g1, g2, g3):
            store.delete_by_ingestion_id(generation)
        with psycopg.connect(dsn) as conn:
            conn.execute(
                "DELETE FROM ingestion_service.document_nodes WHERE repo_id = %s",
                (repo,),
            )
            conn.execute(
                "DELETE FROM ingestion_service.ingestion_requests WHERE repo_id = %s",
                (repo,),
            )
