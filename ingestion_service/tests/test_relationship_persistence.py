# ingestion_service/tests/integration/test_relationship_persistence.py

import pytest
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from shared.models.document_node import DocumentNode
from src.core.crud.document_relationships import (
    create_document_relationship,
    list_relationships_for_document,
)


@pytest.mark.integration
def test_document_relationship_crud(session: Session):
    """
    Integration test for DocumentRelationship persistence (MS3-IS4).

    Verifies:
    - FK integrity
    - Directionality of relationships
    - Unique constraint on (from, to, relation_type)
    
    Uses real Postgres (Docker) and ADR-023 session injection.
    """

    # --- Step 1: Insert two document nodes ---
    node1 = DocumentNode(
        document_id="11111111-1111-1111-1111-111111111111",
        title="Node 1",
    )
    node2 = DocumentNode(
        document_id="22222222-2222-2222-2222-222222222222",
        title="Node 2",
    )
    session.add_all([node1, node2])
    session.commit()  # persist nodes for FK constraints

    # --- Step 2: Create a relationship ---
    rel = create_document_relationship(
        session=session,
        from_document_id=node1.document_id,
        to_document_id=node2.document_id,
        relation_type="supports",
    )
    session.commit()

    # --- Step 3: Verify directionality ---
    outgoing_rels = list_relationships_for_document(
        session, node1.document_id, outgoing=True, incoming=False
    )
    assert len(outgoing_rels) == 1
    assert outgoing_rels[0].from_document_id == node1.document_id
    assert outgoing_rels[0].to_document_id == node2.document_id

    incoming_rels = list_relationships_for_document(
        session, node2.document_id, outgoing=False, incoming=True
    )
    assert len(incoming_rels) == 1
    assert incoming_rels[0].from_document_id == node1.document_id
    assert incoming_rels[0].to_document_id == node2.document_id

    # --- Step 4: Test FK integrity ---
    # Deleting node1 should remove the relationship (ON DELETE CASCADE)
    session.delete(node1)
    session.commit()
    remaining_rels = list_relationships_for_document(session, node2.document_id)
    assert remaining_rels == []

    # --- Step 5: Test unique constraint ---
    # Re-add nodes
    session.add_all([node1, node2])
    session.commit()

    # Add a relationship
    create_document_relationship(session, node1.document_id, node2.document_id, "supports")
    session.commit()

    # Attempt to insert duplicate
    with pytest.raises(IntegrityError):
        create_document_relationship(session, node1.document_id, node2.document_id, "supports")
        session.commit()
