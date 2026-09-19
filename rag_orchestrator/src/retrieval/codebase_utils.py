"""
Utilities for hybrid vector+graph retrieval.
"""
from collections import OrderedDict
from typing import Set, Dict, List, Optional, Tuple
import logging
import threading
import requests
from .codebase_queries import CodebaseGraph, get_repo_generation, load_graph_for_repo
from src.core.config import get_settings




logger = logging.getLogger(__name__)

settings = get_settings()
ingestion_service_url=settings.INGESTION_SERVICE_URL

# #168 (WP-R5): repo_id -> (generation_id, graph), LRU-ordered (most
# recently used last). Guarded by _repo_graphs_lock since concurrent
# requests can call get_cached_graph simultaneously.
_repo_graphs: "OrderedDict[str, Tuple[str, CodebaseGraph]]" = OrderedDict()
_repo_graphs_lock = threading.Lock()
_CACHE_MAX_REPOS = settings.GRAPH_CACHE_MAX_REPOS

def canonical_id_from_metadata(metadata: dict) -> str:
    """
    WP-T1a: single source of truth for pulling canonical_id out of a raw
    vector-search result's metadata dict, checked both flat (ingestion
    writes it directly) and nested under source_metadata (the vector
    store's search response shape) -- used both to populate
    RetrievedChunk.canonical_id at construction time and as the fallback
    for any chunk that predates that field.
    """
    metadata = metadata or {}
    return (
        metadata.get("canonical_id")
        or metadata.get("source_metadata", {}).get("canonical_id")
        or ""
    )


def doc_type_from_metadata(metadata: dict) -> Optional[str]:
    """
    Issue #142 (fix for #141): single source of truth for pulling
    document_nodes.doc_type out of a raw vector-search result's metadata
    dict -- mirrors canonical_id_from_metadata's exact lookup shape
    (checked flat, then nested under source_metadata, since that's the
    vector store's search response shape). Not to be confused with
    source_metadata["source_type"], a different, deliberately-untouched
    field that only separates the /v1/rag vs /v1/rag/simple API paths
    (issue #64) -- doc_type is the one that distinguishes python
    source/rust source/markdown_section/etc.
    """
    metadata = metadata or {}
    return metadata.get("doc_type") or metadata.get("source_metadata", {}).get(
        "doc_type"
    )


def provenance_from_metadata(metadata: dict) -> Optional[dict]:
    """
    Issue #199 (ADR-053, Stage B2): single source of truth for pulling
    the ADR-053 role/subject/derivation/validity/classification envelope
    out of a raw vector-search result's metadata dict -- mirrors
    canonical_id_from_metadata's/doc_type_from_metadata's exact lookup
    shape (checked flat, then nested under source_metadata). Transport
    only: this makes the already-persisted `DocumentNode.provenance`
    (Stage B1) reachable from a retrieved chunk; it does not rank,
    filter, or prefer anything by it. `None` when absent -- a pre-B1
    row or a chunk whose provenance wasn't classified, never guessed.
    """
    metadata = metadata or {}
    return metadata.get("provenance") or metadata.get("source_metadata", {}).get(
        "provenance"
    )


def extract_canonical_ids_from_chunks(chunks: List) -> Set[str]:
    """
    Extract canonical_ids from retrieved chunks, preferring the
    first-class RetrievedChunk.canonical_id field (WP-T1a) and falling
    back to metadata digging for anything constructed without it.
    """
    canonical_ids: Set[str] = set()
    for chunk in chunks:
        cid = getattr(chunk, "canonical_id", None) or canonical_id_from_metadata(
            getattr(chunk, "metadata", {})
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
    return getattr(chunk, "canonical_id", None) or canonical_id_from_metadata(
        getattr(chunk, "metadata", {})
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
    """Thin wrapper over `get_cached_graph_with_generation` for the
    (majority of) callers that only need the graph itself."""
    return get_cached_graph_with_generation(repo_id, force_reload)[1]


def get_cached_graph_with_generation(
    repo_id: str, force_reload: bool = False
) -> Tuple[str, CodebaseGraph]:
    """
    Get CodebaseGraph for repo_id (in-memory cached), keyed on repo_id's
    *current servable generation* (#168 / WP-R5), not repo_id alone.

    Issue #200 (Stage A2): unlike `get_cached_graph`, also returns the
    generation_id the graph was resolved against, so a caller that needs
    a generation fence (verify nothing changed before trusting the
    result) has something to fence against -- `get_cached_graph` alone
    gives no such envelope, which the handoff calls out explicitly as a
    gap. Returns `("", CodebaseGraph())` when nothing is servable; an
    empty generation_id is never a valid fence target, so callers must
    treat it as "not ready," not "matches."

    A re-ingested repo gets a new ingestion_id under the same repo_id; the
    previous implementation kept whichever graph it loaded first forever,
    so a warm worker could keep answering from a stale generation
    indefinitely after a rebuild. get_repo_generation is a cheap check
    (no node/relationship fetch) run on every call, so this can detect a
    generation change without paying for a full graph re-fetch when
    nothing has changed. One generation is resolved once per call and used
    consistently for that call's graph -- callers (hybrid_retrieve calls
    this exactly once per request) therefore never mix two generations'
    graph evidence within a single query.

    Bounded to _CACHE_MAX_REPOS entries (LRU eviction) so the number of
    distinct repositories ever queried cannot grow this cache without
    limit -- the original defect was unbounded growth by repo_id, and
    keying by generation instead of fixing that would just move the same
    problem to "unbounded growth by (repo_id, generation)".
    """
    generation_id, status = get_repo_generation(repo_id)

    if generation_id is None:
        # No completed generation to serve (never ingested, still
        # building, or every attempt failed) -- nothing to cache, and
        # fetching the full graph would only ever return empty per #166.
        if status != "unknown":
            logger.info(
                f"Graph for repo_id={repo_id[:8]} not servable "
                f"(generation_status={status}); returning empty graph"
            )
        return "", CodebaseGraph()

    with _repo_graphs_lock:
        cached = _repo_graphs.get(repo_id)
        if not force_reload and cached is not None and cached[0] == generation_id:
            _repo_graphs.move_to_end(repo_id)
            return generation_id, cached[1]

    logger.info(
        f"Loading graph for repo_id={repo_id[:8]} generation={generation_id[:8]}..."
    )
    graph = load_graph_for_repo(repo_id)
    logger.info(f"Graph loaded: {len(graph.nodes)} nodes")

    with _repo_graphs_lock:
        _repo_graphs[repo_id] = (generation_id, graph)
        _repo_graphs.move_to_end(repo_id)
        while len(_repo_graphs) > _CACHE_MAX_REPOS:
            evicted_repo_id, _ = _repo_graphs.popitem(last=False)
            logger.info(f"Evicted cached graph for repo_id={evicted_repo_id[:8]}")
    return generation_id, graph
