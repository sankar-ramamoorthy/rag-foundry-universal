# ingestion_service/src/core/crud/crud_document_node.py

from typing import List, Optional
from uuid import UUID
import logging

from sqlalchemy.orm import Session
from shared.models.document_node import DocumentNode

# Set up logging
logger = logging.getLogger(__name__)
logging.basicConfig(level=logging.WARNING)


def create_document_node(
    session: Session,
    *,
    document_id: UUID,
    title: str,
    summary: str,
    source: str,
    ingestion_id: UUID,
    doc_type: str,
    canonical_id: str,           # ← ADD THIS
    relative_path: str,          # ← ADD THIS
    repo_id: Optional[str] = None,  
) -> DocumentNode:
    """
    Create and persist a new DocumentNode.

    This function does NOT create sessions or engines.
    """
    # Validate title before creating the document node
    if not title:
        logger.warning("Title is empty or None. Defaulting to 'Untitled Document'.")
        title = "Untitled Document"  # Default title if not provided
    
    # Validate summary before creating the document node
    if not summary:
        logger.warning("Summary is empty or None. Defaulting to 'Summary pending'.")
        summary = "Summary pending"  # Default summary if not provided
    
    # Log the data to check before insertion
    logger.debug(f"Creating DocumentNode with data: "
                 f"document_id={document_id}, title={title}, summary={summary}, "
                 f"source={source}, ingestion_id={ingestion_id}, doc_type={doc_type}, repo_id={repo_id}")

    # Create and persist the DocumentNode
    node = DocumentNode(
        document_id=document_id,
        title=title,
        summary=summary,
        source=source,
        ingestion_id=ingestion_id,
        doc_type=doc_type,
        canonical_id=canonical_id,       # ✅
        relative_path=relative_path,     # ✅
        repo_id=repo_id or str(ingestion_id),  # Use ingestion_id if repo_id is None
    )

    session.add(node)
    session.commit()
    session.refresh(node)

    logger.debug(f"DocumentNode {document_id} created and committed.")
    return node


def get_document_node(
    session: Session,
    document_id: UUID,
) -> Optional[DocumentNode]:
    """
    Retrieve a DocumentNode by its ID.
    """
    return (
        session.query(DocumentNode)
        .filter(DocumentNode.document_id == document_id)
        .one_or_none()
    )


def list_document_nodes_by_ingestion(
    session: Session,
    ingestion_id: UUID,
) -> List[DocumentNode]:
    """
    List all DocumentNodes produced by a given ingestion request.
    """
    return (
        session.query(DocumentNode)
        .filter(DocumentNode.ingestion_id == ingestion_id)
        .order_by(DocumentNode.document_id)
        .all()
    )


def update_document_node_summary(
    session, ingestion_id: UUID, summary: str
) -> bool:
    """MS7-IS3: Update document_node.summary by ingestion_id."""
    
    doc = (session.query(DocumentNode)
           .filter_by(ingestion_id=ingestion_id)
           .first())
    
    if doc:
        doc.summary = summary
        session.commit()
        return True
    return False
