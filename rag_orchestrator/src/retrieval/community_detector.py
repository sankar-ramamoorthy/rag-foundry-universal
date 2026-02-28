# rag_orchestrator/src/retrieval/community_detector.py

from typing import List, Dict, Optional, Any
from collections import defaultdict


def cluster_documents(
    document_ids: List[str],
    metadata: Optional[Dict[str, Dict[str, Any]]] = None,
    cluster_by: str = "project_phase",
) -> List[List[str]]:
    """
    Deterministically cluster documents by a metadata field.

    Args:
        document_ids: List of document IDs to cluster
        metadata: Optional dict mapping document_id -> metadata dict
        cluster_by: Metadata key to cluster on (default 'project_phase')

    Returns:
        List of clusters, each a list of document_ids.
        Clusters are sorted alphabetically by key, documents alphabetically.
        Deterministic across runs.
    """
    if not document_ids:
        return []

    # If no metadata provided, treat all documents as one cluster
    if metadata is None:
        return [sorted(document_ids)]

    # Build clusters based on metadata[cluster_by]
    clusters_map: Dict[str, List[str]] = defaultdict(list)
    for doc_id in document_ids:
        doc_meta = metadata.get(doc_id, {})
        key = str(doc_meta.get(cluster_by, "UNKNOWN"))
        clusters_map[key].append(doc_id)

    # Sort clusters by key, documents within clusters alphabetically
    clusters = [
        sorted(docs) for key, docs in sorted(clusters_map.items(), key=lambda x: x[0])
    ]

    return clusters
