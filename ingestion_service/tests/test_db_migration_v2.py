import pytest
from src.core.database_session import get_engine

@pytest.mark.integration
def test_document_nodes_table_exists_sql():
    engine = get_engine()
    with engine.connect() as conn:
        result = conn.execute(
            """
            SELECT table_name
            FROM information_schema.tables
            WHERE table_schema='public';
            """
        )
        tables = [row[0] for row in result]
    assert "document_nodes" in tables, f"'document_nodes' table not found. Found: {tables}"
