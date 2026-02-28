# tests/test_document_node_crud_integration.py

import uuid
import pytest
from sqlalchemy import inspect

from src.core.crud import (
    create_document_node,
    get_document_node,
)
from src.core.codebase.identity import build_repo_id
# ---------------------------------------------------------------------------
# Schema validation (MS2-IS4 requirement)
# For the above test to work, conftest.py must provide:
#engine   # SQLAlchemy Engine (DB-backed)
#session  # SQLAlchemy Session bound to that engine
#These fixtures must:
#  Use DATABASE_URL from environment
#  Point to test DB
#  Not auto-create schema (Alembic owns schema)
# ---------------------------------------------------------------------------

@pytest.mark.docker
@pytest.mark.integration
def test_document_nodes_table_exists(engine):
    """
    Verify that Alembic migrations have created the document_nodes table.
    This test fails fast if migrations were not applied.
    """
    inspector = inspect(engine)
    tables = inspector.get_table_names(schema="ingestion_service")

    assert "document_nodes" in tables, (
        "document_nodes table does not exist. "
        "Have Alembic migrations been applied?"
    )


# ---------------------------------------------------------------------------
# CRUD integration test
# ---------------------------------------------------------------------------

@pytest.mark.docker
@pytest.mark.integration
def test_document_node_crud(session):
    """
    End-to-end CRUD validation for DocumentNode ORM model.
    Uses real Postgres + pgvector.
    """

    document_id = str(uuid.uuid4())

    node = create_document_node(
        session=session,
        document_id=document_id,
        ingestion_id="ingest-1",
        title="CRUD Test",
        text="Lorem Ipsum",
        metadata={},
        repo_id = build_repo_id(repo_url), 
    )

    assert node.document_id == document_id

    fetched = get_document_node(session, document_id)
    assert fetched is not None
    assert fetched.document_id == document_id
    assert fetched.title == "CRUD Test"
    assert fetched.text == "Lorem Ipsum"
