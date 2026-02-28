# ingestion_service/src/core/graph_utils.py

"""
Graph utilities for ingestion_service.

Provides:
- In-memory CodebaseGraph for a repo
- Node and edge representation
- Functions to load from DB
- Mapping canonical_ids → document_ids
"""

from collections import defaultdict
from typing import Dict, Set, Optional
from sqlalchemy.orm import Session
import logging

from shared.models import DocumentNode, DocumentRelationship

logger = logging.getLogger(__name__)

# -------------------------------
# Node & Graph Classes
# -------------------------------

class Node:
    """
    Represents a single artifact node in the graph.
    """
    def __init__(self, canonical_id: str, file_path: Optional[str] = None, lineno: Optional[int] = None):
        self.canonical_id = canonical_id
        self.file_path = file_path
        self.lineno = lineno
        self.out_edges: Dict[str, Set['Node']] = defaultdict(set)  # relation_type -> set of target nodes
        self.in_edges: Dict[str, Set['Node']] = defaultdict(set)   # relation_type -> set of source nodes

    def __repr__(self):
        return f"Node({self.canonical_id})"


class CodebaseGraph:
    """
    In-memory representation of a codebase's canonical artifact graph.
    """
    def __init__(self):
        self.nodes: Dict[str, Node] = {}

    def add_node(self, node: Node):
        self.nodes[node.canonical_id] = node

    def add_edge(self, from_cid: str, to_cid: str, relation_type: str):
        from_node = self.nodes.get(from_cid)
        to_node = self.nodes.get(to_cid)
        if not from_node or not to_node:
            raise ValueError(f"Cannot add edge: {from_cid} -> {to_cid}")
        from_node.out_edges[relation_type].add(to_node)
        to_node.in_edges[relation_type].add(from_node)

    def get_node(self, canonical_id: str) -> Optional[Node]:
        return self.nodes.get(canonical_id)


# -------------------------------
# Global Graph Cache
# -------------------------------
_repo_graphs: Dict[str, CodebaseGraph] = {}


# -------------------------------
# DB Loading Functions
# -------------------------------

def load_graph_for_repo(repo_id: str, db: Session) -> CodebaseGraph:
    """
    Build an in-memory CodebaseGraph from persisted DocumentNode and DocumentRelationship entries.
    """
    graph = CodebaseGraph()

    # Load nodes
    nodes = db.query(DocumentNode).filter(DocumentNode.repo_id == repo_id).all()
    if not nodes:
        return graph

    id_to_canonical: Dict[str, str] = {}

    for node in nodes:
        n = Node(
            canonical_id=node.canonical_id,
            file_path=getattr(node, "relative_path", None),
            lineno=getattr(node, "lineno", None)
        )
        graph.add_node(n)
        id_to_canonical[node.document_id] = node.canonical_id

    # Load relationships
    relationships = db.query(DocumentRelationship)\
                      .filter(DocumentRelationship.from_document_id.in_(id_to_canonical.keys()))\
                      .all()

    for rel in relationships:
        from_cid = id_to_canonical.get(rel.from_document_id)
        to_cid = id_to_canonical.get(rel.to_document_id)
        if from_cid and to_cid:
            graph.add_edge(from_cid, to_cid, rel.relation_type)

    return graph


def canonical_ids_to_document_ids(repo_id: str, canonical_ids: Set[str], db: Session) -> Set[str]:
    """
    Convert canonical_ids → document_ids for a repo.
    """
    if not canonical_ids:
        return set()

    document_ids = {
        node.document_id
        for node in db.query(DocumentNode)
        .filter(DocumentNode.repo_id == repo_id)
        .filter(DocumentNode.canonical_id.in_(canonical_ids))
        .all()
    }

    logger.debug(f"Resolved {len(canonical_ids)} canonical_ids → {len(document_ids)} document_ids")
    return document_ids


def get_cached_graph(repo_id: str, db: Session, force_reload: bool = False) -> CodebaseGraph:
    """
    Return a CodebaseGraph for the given repo_id, using an in-memory cache.
    """
    global _repo_graphs

    if force_reload or repo_id not in _repo_graphs:
        logger.info(f"Loading graph for repo_id={repo_id[:8]}...")
        _repo_graphs[repo_id] = load_graph_for_repo(repo_id, db)
        logger.info(f"Graph loaded: {len(_repo_graphs[repo_id].nodes)} nodes")

    return _repo_graphs[repo_id]