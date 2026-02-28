# tests/test_crud_document_relationships.py
import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from shared.models.base import Base
from shared.models.document_node import DocumentNode
from src.core.crud import document_relationships as crud

# -----------------------------
# Fixtures
# -----------------------------

@pytest.fixture(scope="module")
def engine():
    # Use in-memory SQLite for fast unit testing
    engine = create_engine("sqlite:///:memory:", echo=False)
    Base.metadata.create_all(engine)
    return engine

@pytest.fixture(scope="function")
def session(engine):
    """Provide a transactional scope around a series of operations."""
    connection = engine.connect()
    transaction = connection.begin()
    Session = sessionmaker(bind=connection)
    session = Session()

    yield session

    session.close()
    transaction.rollback()
    connection.close()


@pytest.fixture
def sample_document(session):
    """Create a sample DocumentNode for relationship testing."""
    doc = DocumentNode(
        title="Doc 1",
        summary="Summary",
        source="unit-test",
        ingestion_id="test-ingest",
        doc_type="pdf"
    )
    session.add(doc)
    session.flush()
    return doc


# -----------------------------
# Tests
# -----------------------------

def test_create_relationship(session, sample_document):
    doc1 = sample_document
    doc2 = DocumentNode(
        title="Doc 2",
        summary="Another summary",
        source="unit-test",
        ingestion_id="test-ingest",
        doc_type="pdf"
    )
    session.add(doc2)
    session.flush()

    rel = crud.create_document_relationship(
        session=session,
        from_document_id=doc1.document_id,
        to_document_id=doc2.document_id,
        relation_type="supports",
        metadata={"confidence": 0.9},
    )

    assert rel.id is not None
    assert rel.from_document_id == doc1.document_id
    assert rel.to_document_id == doc2.document_id
    assert rel.relation_type == "supports"
    assert rel.metadata["confidence"] == 0.9


def test_list_relationships(session, sample_document):
    doc1 = sample_document
    doc2 = DocumentNode(
        title="Doc 2",
        summary="Another summary",
        source="unit-test",
        ingestion_id="test-ingest",
        doc_type="pdf"
    )
    session.add(doc2)
    session.flush()

    # Create two relationships
    rel1 = crud.create_document_relationship(session, doc1.document_id, doc2.document_id, "supports")
    rel2 = crud.create_document_relationship(session, doc2.document_id, doc1.document_id, "refutes")

    # Test outgoing
    outgoing = crud.list_relationships_for_document(session, doc1.document_id, outgoing=True, incoming=False)
    assert rel1 in outgoing
    assert rel2 not in outgoing

    # Test incoming
    incoming = crud.list_relationships_for_document(session, doc1.document_id, outgoing=False, incoming=True)
    assert rel2 in incoming
    assert rel1 not in incoming

    # Test all
    all_rels = crud.list_relationships_for_document(session, doc1.document_id, outgoing=True, incoming=True)
    assert set(all_rels) == {rel1, rel2}


def test_delete_relationship(session, sample_document):
    doc1 = sample_document
    doc2 = DocumentNode(
        title="Doc 2",
        summary="Another summary",
        source="unit-test",
        ingestion_id="test-ingest",
        doc_type="pdf"
    )
    session.add(doc2)
    session.flush()

    rel = crud.create_document_relationship(session, doc1.document_id, doc2.document_id, "supports")
    rel_id = rel.id

    crud.delete_document_relationship(session, rel_id)

    # Should no longer exist
    fetched = crud.list_relationships_for_document(session, doc1.document_id)
    assert rel not in fetched
