# tests/test_document_node_model.py
import pytest
from shared.models.document_node import DocumentNode

@pytest.mark.docker
@pytest.mark.integration
def test_document_node_roundtrip(session):
    node = DocumentNode(
        document_id="test-id",
        ingestion_id="ingest-1",
        title="Test Document",
        text="Hello world",
        metadata={},
    )
    session.add(node)
    session.commit()

    loaded = session.get(DocumentNode, "test-id")
    assert loaded is not None
    assert loaded.title == "Test Document"
