# ingestion_service/src/core/crud/document_relationships.py
"""
CRUD functions for DocumentRelationship ORM.

All functions are **session-injected** (ADR-023 compliant) and operate directly
on the database. No graph traversal, no validation, no business logic.
"""

from typing import List
from sqlalchemy.orm import Session

from shared.models.document_relationship import DocumentRelationship


def create_document_relationship(
    session: Session,
    from_document_id: str,
    to_document_id: str,
    relation_type: str,
    metadata: dict | None = None
) -> DocumentRelationship:
    """
    Create a new DocumentRelationship record.

    Args:
        session: SQLAlchemy Session, injected by caller.
        from_document_id: UUID of the source DocumentNode.
        to_document_id: UUID of the target DocumentNode.
        relation_type: Type of relationship (arbitrary string).
        metadata: Optional JSON metadata dict.

    Returns:
        The newly created DocumentRelationship instance.
    """
    relationship = DocumentRelationship(
        from_document_id=from_document_id,
        to_document_id=to_document_id,
        relation_type=relation_type,
        metadata=metadata or {},
    )
    session.add(relationship)
    session.flush()  # populate ID without commit
    return relationship


def list_relationships_for_document(
    session: Session,
    document_id: str,
    outgoing: bool = True,
    incoming: bool = True
) -> List[DocumentRelationship]:
    """
    List relationships associated with a document.

    Args:
        session: SQLAlchemy Session, injected by caller.
        document_id: DocumentNode UUID.
        outgoing: Include relationships where this document is the source.
        incoming: Include relationships where this document is the target.

    Returns:
        List of DocumentRelationship instances.
    """
    query = session.query(DocumentRelationship)

    if outgoing and incoming:
        query = query.filter(
            (DocumentRelationship.from_document_id == document_id) |
            (DocumentRelationship.to_document_id == document_id)
        )
    elif outgoing:
        query = query.filter(DocumentRelationship.from_document_id == document_id)
    elif incoming:
        query = query.filter(DocumentRelationship.to_document_id == document_id)
    else:
        return []

    return query.all()


def delete_document_relationship(
    session: Session,
    relationship_id: int
) -> None:
    """
    Delete a DocumentRelationship by ID.

    Args:
        session: SQLAlchemy Session, injected by caller.
        relationship_id: Primary key of the DocumentRelationship.

    Returns:
        None
    """
    session.query(DocumentRelationship).filter_by(id=relationship_id).delete()
    session.flush()

def list_outgoing_relationships(session: Session, document_id: str) -> list[DocumentRelationship]:
    """
    Return all outgoing relationships from a given document.

    Args:
        session: SQLAlchemy Session (injected)
        document_id: UUID of the source DocumentNode

    Returns:
        List of DocumentRelationship instances where `from_document_id` == document_id
    """
    return session.query(DocumentRelationship).filter_by(from_document_id=document_id).all()
