# ingestion_service/src/api/v1/graph.py

from fastapi import APIRouter, HTTPException, Query
from typing import List, Dict
from pydantic import BaseModel
import logging

from src.core import db_utils

router = APIRouter(prefix="/graph", tags=["graph"])
logger = logging.getLogger(__name__)


# -------------------------------
# Response Models
# -------------------------------

class GraphNode(BaseModel):
    document_id: str
    canonical_id: str
    relative_path: str
    title: str
    doc_type: str


class CanonicalLookupResponse(BaseModel):
    nodes: List[GraphNode]
    total: int


class FullGraphResponse(BaseModel):
    nodes: List[GraphNode]
    relationships: Dict
    total_nodes: int

# New models for document relationships endpoint
class RelationshipItem(BaseModel):
    target_document_id: str
    relation_type: str


class DocumentRelationshipsResponse(BaseModel):
    document_id: str
    relationships: List[RelationshipItem]
    total: int



# -------------------------------
# GET /graph/repos/{repo_id}/nodes
# -------------------------------

@router.get("/repos/{repo_id}/nodes", response_model=CanonicalLookupResponse)
async def get_nodes_by_canonical_ids(
    repo_id: str,
    canonical_ids: str = Query(..., description="Comma-separated canonical_ids"),
):
    """
    Convert canonical_ids → document_ids for graph traversal.

    Example:
        /v1/graph/repos/<repo_id>/nodes?canonical_ids=file.py,file.py#function
    """
    if not canonical_ids.strip():
        raise HTTPException(400, "canonical_ids required")

    cids = [cid.strip() for cid in canonical_ids.split(",") if cid.strip()]

    if not cids:
        return CanonicalLookupResponse(nodes=[], total=0)

    logger.debug(f"Graph lookup: repo={repo_id[:8]}, cids={len(cids)}")

    nodes = db_utils.get_document_nodes_by_canonical_ids(repo_id, cids)

    result = [
        GraphNode(
            document_id=str(node.document_id),
            canonical_id=node.canonical_id,
            relative_path=node.relative_path or "",
            title=node.title or "",
            doc_type=node.doc_type or "",
        )
        for node in nodes
    ]

    logger.info(f"Graph lookup: {len(cids)} canonical_ids → {len(result)} nodes")

    return CanonicalLookupResponse(nodes=result, total=len(result))


# -------------------------------
# GET /graph/repos/{repo_id}
# -------------------------------

@router.get("/repos/{repo_id}", response_model=FullGraphResponse)
async def get_full_graph(
    repo_id: str,
):
    """
    Export the entire graph (nodes and relationships) for the given repository.

    Returns:
        nodes: list of GraphNode
        relationships: dict of {from_canonical_id: [{to_canonical_id, relation_type}]}
        total_nodes: int

    Example:
        /v1/graph/repos/<repo_id>
    """
    logger.debug(f"Graph export: repo={repo_id[:8]}")

    graph_data = db_utils.get_full_graph_for_repo(repo_id)

    # graph_data["nodes"] is dict: canonical_id → DocumentNode ORM object
    nodes = [
        GraphNode(
            document_id=str(node.document_id),   # cast UUID → str
            canonical_id=node.canonical_id,
            relative_path=node.relative_path or "",
            title=node.title or "",
            doc_type=node.doc_type or "",
        )
        for canonical_id, node in graph_data["nodes"].items()
    ]

    logger.info(
        f"Graph export: repo={repo_id[:8]} — "
        f"{len(nodes)} nodes, "
        f"{len(graph_data['relationships'])} relationship groups"
    )

    return FullGraphResponse(
        nodes=nodes,
        relationships=graph_data["relationships"],
        total_nodes=len(nodes),
    )


# GET /graph/docs/{document_id}/relationships
@router.get("/docs/{document_id}/relationships", 
            response_model=DocumentRelationshipsResponse)
async def get_document_relationships(
    document_id: str,
):
    """
    Return outgoing relationships for a single document.
    Used by rag_orchestrator simple_service to expand retrieval plan
    via traversal_planner.expand_retrieval_plan().

    Example:
        /v1/graph/docs/486dcf66-c9ba-4f99-9dd6-296e81039c48/relationships
    """
    logger.debug(f"Relationships lookup: document_id={document_id[:8]}")

    from src.core.database_session import get_sessionmaker
    from src.core.crud.document_relationships import list_outgoing_relationships

    SessionLocal = get_sessionmaker()

    with SessionLocal() as session:
        rels = list_outgoing_relationships(session, document_id=document_id)

    result = [
        RelationshipItem(
            target_document_id=str(rel.to_document_id),
            relation_type=rel.relation_type,
        )
        for rel in rels
    ]

    logger.info(
        f"Relationships lookup: document_id={document_id[:8]} "
        f"→ {len(result)} outgoing relationships"
    )

    return DocumentRelationshipsResponse(
        document_id=document_id,
        relationships=result,
        total=len(result),
    )
