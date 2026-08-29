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
    logger.debug(
        f"Extracted {len(canonical_ids)} canonical_ids from {len(chunks)} chunks"
    )
    return canonical_ids


def _relative_path_of(chunk) -> str:
    metadata = getattr(chunk, "metadata", {}) or {}
    return (
        metadata.get("relative_path")
        or metadata.get("source_metadata", {}).get("relative_path")
        or ""
    )


def _canonical_id_of(chunk) -> str:
    metadata = getattr(chunk, "metadata", {}) or {}
    return (
        metadata.get("canonical_id")
        or metadata.get("source_metadata", {}).get("canonical_id")
        or ""
    )


def _normalize_for_dedup(text: str) -> str:
    return " ".join((text or "").split())


def _is_near_duplicate_text(
    text_a: str, text_b: str, min_containment_ratio: float = 0.85
) -> bool:
    """True when the shorter (normalized) text is almost entirely
    contained in the longer one.

    This is the exact relationship a container artifact's text has with
    its sole child's (a module ⊇ its only class/function; a markdown
    module ⊇ its only H1 section) — both are literal slices of the same
    underlying source, so containment is the precise, cheap test rather
    than an approximate similarity metric.
    """
    a = _normalize_for_dedup(text_a)
    b = _normalize_for_dedup(text_b)
    if not a or not b:
        return False
    shorter, longer = (a, b) if len(a) <= len(b) else (b, a)
    if shorter not in longer:
        return False
    return len(shorter) / len(longer) >= min_containment_ratio


def _pick_duplicate_to_drop(a, b):
    """Of a near-duplicate pair, the one to drop: lower vector-search
    score loses (it's the weaker candidate for *this* query); on a tie,
    drop the less specific artifact (shallower canonical_id)."""
    score_a = a.score if a.score is not None else -1.0
    score_b = b.score if b.score is not None else -1.0
    if score_a != score_b:
        return a if score_a < score_b else b
    depth_a = _canonical_id_of(a).count("#") + _canonical_id_of(a).count(".")
    depth_b = _canonical_id_of(b).count("#") + _canonical_id_of(b).count(".")
    return a if depth_a < depth_b else b


def dedupe_near_identical_chunks(
    chunks: List, min_containment_ratio: float = 0.85
) -> List:
    """
    Issue #65: a module/root artifact with exactly one child covering
    (almost) the same text produces near-duplicate embeddings — e.g. a
    README.md's markdown_module vs. its sole H1 markdown_section, or a
    single-class module vs. that class. Both land in the seed candidate
    set competing for the same top-k slots with effectively the same
    content, crowding out genuinely different candidates.

    Drops the lower-scoring chunk of each near-duplicate pair found
    within the same source file (relative_path), keeping the
    higher-scoring one. Comparison is pairwise within each
    relative_path group, so it works whether or not artifact text was
    further split into sub-chunks (matching sub-chunks pair up on
    their own).
    """
    by_path: Dict[str, List] = {}
    for chunk in chunks:
        by_path.setdefault(_relative_path_of(chunk), []).append(chunk)

    dropped_chunk_ids: Set[str] = set()
    for path, group in by_path.items():
        if not path or len(group) < 2:
            continue
        for i in range(len(group)):
            for j in range(i + 1, len(group)):
                a, b = group[i], group[j]
                if a.chunk_id in dropped_chunk_ids or b.chunk_id in dropped_chunk_ids:
                    continue
                if not _is_near_duplicate_text(
                    a.text, b.text, min_containment_ratio
                ):
                    continue
                dropped_chunk_ids.add(_pick_duplicate_to_drop(a, b).chunk_id)

    if dropped_chunk_ids:
        logger.info(
            f"🧹 Dropped {len(dropped_chunk_ids)} near-duplicate seed "
            f"chunk(s) (issue #65)"
        )
    return [c for c in chunks if c.chunk_id not in dropped_chunk_ids]


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
        document_ids = {
            node["document_id"] for node in response.json().get("nodes", [])
        }
        logger.debug(
            f"Resolved {len(canonical_ids)} canonical_ids → "
            f"{len(document_ids)} document_ids"
        )
        return document_ids
    else:
        logger.error(
            f"Error resolving canonical_ids: {response.status_code} - {response.text}"
        )
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
