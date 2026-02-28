"""
Utilities for hybrid vector+graph retrieval.
"""
from typing import Set, Dict, List
import logging
import requests
from .codebase_queries import CodebaseGraph, load_graph_for_repo
from src.core.config import get_settings    
        



logger = logging.getLogger(__name__)

_repo_graphs: Dict[str, CodebaseGraph] = {}
settings = get_settings()
ingestion_service_url=settings.INGESTION_SERVICE_URL

def extract_canonical_ids_from_chunks(chunks: List) -> Set[str]:
    """
    Extract canonical_ids from retrieved chunk metadata.
    """
    canonical_ids: Set[str] = set()
    for chunk in chunks:
        metadata = getattr(chunk, "metadata", {}) or {}
        cid = (
            metadata.get("canonical_id")
            or metadata.get("source_metadata", {}).get("canonical_id")
        )
        if cid:
            canonical_ids.add(cid)
    logger.debug(f"Extracted {len(canonical_ids)} canonical_ids from {len(chunks)} chunks")
    return canonical_ids


def canonical_ids_to_document_ids(
    repo_id: str,
    canonical_ids: Set[str]
) -> Set[str]:
    """
    Convert canonical_ids → document_ids for a repo using ingestion_service API.
    """
    if not canonical_ids:
        return set()
    url = f"{ingestion_service_url}/v1/graph/repos/{repo_id}/nodes"
    response = requests.get(url, params={"canonical_ids": ",".join(canonical_ids)})
    if response.status_code == 200:
        document_ids = {node['document_id'] for node in response.json().get("nodes", [])}
        logger.debug(f"Resolved {len(canonical_ids)} canonical_ids → {len(document_ids)} document_ids")
        return document_ids
    else:
        logger.error(f"Error resolving canonical_ids: {response.status_code} - {response.text}")
        return set()


def get_cached_graph(repo_id: str, force_reload: bool = False) -> CodebaseGraph:
    """
    Get CodebaseGraph for repo_id (in-memory cached).
    """
    global _repo_graphs
    if force_reload or repo_id not in _repo_graphs:
        logger.info(f"Loading graph for repo_id={repo_id[:8]}...")
        _repo_graphs[repo_id] = load_graph_for_repo(repo_id)
        logger.info(f"Graph loaded: {len(_repo_graphs[repo_id].nodes)} nodes")
    return _repo_graphs[repo_id]