# ingestion_service/tests/test_db_migrations.py
import pytest
from sqlalchemy import inspect
from src.core.database_session import get_engine

@pytest.mark.integration
def test_document_nodes_table_exists():
    """
    Ensure the 'document_nodes' table exists after migrations.
    """
    engine = get_engine()
    inspector = inspect(engine)
    tables = inspector.get_table_names()
    
    assert "document_nodes" in tables, (
        f"'document_nodes' table not found in database. Existing tables: {tables}"
    )
