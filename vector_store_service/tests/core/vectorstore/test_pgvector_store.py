# tests/core/vectorstore/test_pgvector_store.py
from unittest.mock import patch, MagicMock
import pytest

from src.core.vectorstore.pgvector_store import PgVectorStore
from shared.models.vector import VectorRecord, VectorMetadata


class TestPgVectorStore:
    @patch("src.core.vectorstore.pgvector_store.psycopg.connect")
    def test_add_vectors_calls_execute(self, mock_connect):
        """Ensure add() calls cursor.execute once per record."""

        # Setup mocks
        mock_cursor = MagicMock()
        mock_conn = MagicMock()
        mock_conn.cursor.return_value.__enter__.return_value = mock_cursor
        mock_connect.return_value.__enter__.return_value = mock_conn

        # Patch _validate_table at instantiation to avoid RuntimeError
        with patch.object(PgVectorStore, "_validate_table", lambda self: None):
            store = PgVectorStore(dsn="mock_dsn", dimension=768)

        records = [
            VectorRecord(
                vector=[0.1, 0.2],
                metadata=VectorMetadata(
                    ingestion_id="ing_1",
                    chunk_id="c1",
                    chunk_index=0,
                    chunk_strategy="paragraph",
                    chunk_text="text chunk",
                    source_metadata={},
                    provider="mock",
                ),
            )
        ]

        store.add(records)

        # Only count INSERT statements
        insert_calls = [
            call for call in mock_cursor.execute.call_args_list
            if "INSERT INTO" in str(call)
        ]
        assert len(insert_calls) == len(records)

    @patch("src.core.vectorstore.pgvector_store.psycopg.connect")
    def test_delete_by_ingestion_id_calls_execute(self, mock_connect):
        """Ensure delete_by_ingestion_id executes DELETE SQL."""

        mock_cursor = MagicMock()
        mock_conn = MagicMock()
        mock_conn.cursor.return_value.__enter__.return_value = mock_cursor
        mock_connect.return_value.__enter__.return_value = mock_conn

        with patch.object(PgVectorStore, "_validate_table", lambda self: None):
            store = PgVectorStore(dsn="mock_dsn", dimension=768)

        store.delete_by_ingestion_id("ing_123")

        # Only count DELETE statements
        delete_calls = [
            call for call in mock_cursor.execute.call_args_list
            if "DELETE FROM" in str(call)
        ]
        assert len(delete_calls) == 1

