# tests/core/vectorstore/test_pgvector_store.py
from unittest.mock import patch, MagicMock
import pytest

from src.core.vectorstore.pgvector_store import PgVectorStore
from shared.models.vector import VectorRecord, VectorMetadata

pytestmark = pytest.mark.unit


def _record(document_id=None) -> VectorRecord:
    return VectorRecord(
        vector=[0.1, 0.2],
        metadata=VectorMetadata(
            ingestion_id="ing_1",
            chunk_id="c1",
            chunk_index=0,
            chunk_strategy="paragraph",
            chunk_text="text chunk",
            source_metadata={},
            provider="mock",
            document_id=document_id,
        ),
    )


def _mock_cursor(mock_connect):
    mock_cursor = MagicMock()
    mock_conn = MagicMock()
    mock_conn.cursor.return_value.__enter__.return_value = mock_cursor
    mock_connect.return_value.__enter__.return_value = mock_conn
    return mock_cursor


def _insert_statements(mock_cursor):
    """Return the SQL text of every INSERT executed on the cursor."""
    return [
        str(call.args[0])
        for call in mock_cursor.execute.call_args_list
        if "INSERT INTO" in str(call.args[0])
    ]


class TestPgVectorStore:
    @patch("src.core.vectorstore.pgvector_store.psycopg.connect")
    def test_add_writes_once_per_record(self, mock_connect):
        """F-15: exactly ONE insert per record — the dual-write is retired."""
        mock_cursor = _mock_cursor(mock_connect)
        store = PgVectorStore(dsn="mock_dsn", dimension=1024)

        records = [_record(document_id="doc-1")]
        store.add(records)

        inserts = _insert_statements(mock_cursor)
        assert len(inserts) == len(records)

    @patch("src.core.vectorstore.pgvector_store.psycopg.connect")
    def test_add_targets_only_vector_chunks(self, mock_connect):
        """F-15: inserts go to vector_chunks; the legacy vectors table is
        never written."""
        mock_cursor = _mock_cursor(mock_connect)
        store = PgVectorStore(dsn="mock_dsn", dimension=1024)

        store.add([_record(document_id="doc-1"), _record(document_id=None)])

        inserts = _insert_statements(mock_cursor)
        assert inserts, "No INSERT was executed"
        for stmt in inserts:
            assert "vector_chunks" in stmt
            assert ".vectors" not in stmt, (
                f"Legacy vectors table still written: {stmt}"
            )

    @patch("src.core.vectorstore.pgvector_store.psycopg.connect")
    def test_add_without_document_id_still_persisted(self, mock_connect):
        """A record with no document_id must still land in vector_chunks
        (column is nullable) — it must not be dropped."""
        mock_cursor = _mock_cursor(mock_connect)
        store = PgVectorStore(dsn="mock_dsn", dimension=1024)

        store.add([_record(document_id=None)])

        inserts = [
            call for call in mock_cursor.execute.call_args_list
            if "INSERT INTO" in str(call.args[0])
        ]
        assert len(inserts) == 1
        assert "vector_chunks" in str(inserts[0].args[0])
        # document_id is the last parameter and must be NULL, not omitted
        assert inserts[0].args[1][-1] is None

    @patch("src.core.vectorstore.pgvector_store.psycopg.connect")
    def test_delete_by_ingestion_id_purges_vector_chunks(self, mock_connect):
        """delete still purges vector_chunks (and the legacy table until a
        migration drops it)."""
        mock_cursor = _mock_cursor(mock_connect)
        store = PgVectorStore(dsn="mock_dsn", dimension=1024)

        store.delete_by_ingestion_id("ing_123")

        delete_stmts = [
            str(call.args[0])
            for call in mock_cursor.execute.call_args_list
            if "DELETE FROM" in str(call.args[0])
        ]
        assert any("vector_chunks" in stmt for stmt in delete_stmts)
