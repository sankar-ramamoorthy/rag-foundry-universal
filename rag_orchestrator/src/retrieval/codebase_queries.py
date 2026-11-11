from collections import deque, defaultdict
from typing import List, Set, Dict, Optional, NoReturn
from uuid import UUID
from fastapi import HTTPException
import requests  # New import to call the ingestion service API
from src.core.config import get_settings
import logging

# Set up logging configuration
logging.basicConfig(level=logging.WARNING)
logger = logging.getLogger(__name__)

settings = get_settings()
ingestion_service_url = settings.INGESTION_SERVICE_URL


# --- Graph Classes ---
class Node:
    """
    Represents a single artifact node in the graph.
    """

    def __init__(
        self,
        canonical_id: str,
        file_path: str,
        lineno: Optional[int] = None,
        provenance: Optional[dict] = None,
    ):
        self.canonical_id = canonical_id
        self.file_path = file_path
        self.lineno = lineno
        # Issue #199 (ADR-053, Stage C prerequisite): transport only, from
        # the graph API's GraphNode.provenance. None for a pre-B1 row or a
        # Node constructed without it (e.g. every existing test fixture).
        self.provenance = provenance
        self.out_edges: Dict[str, Set["Node"]] = defaultdict(
            set
        )  # relation_type -> set of target nodes
        self.in_edges: Dict[str, Set["Node"]] = defaultdict(
            set
        )  # relation_type -> set of source nodes

    def __repr__(self):
        return f"Node({self.canonical_id})"


class CodebaseGraph:
    """
    In-memory representation of a codebase's canonical artifact graph.
    """

    def __init__(self):
        self.repo_id: Optional[str] = None
        self.ingestion_id: Optional[str] = None
        self.nodes: Dict[str, Node] = {}
        # Issue #220: per-edge relationship_metadata (confidence,
        # call_sites, bases, etc. -- see graph_assembler.py), keyed by the
        # directed (from_canonical_id, to_canonical_id, relation_type)
        # triple. Deliberately NOT stored on Node.out_edges/in_edges
        # itself (those stay Dict[relation_type, Set[Node]] exactly as
        # before) -- every existing consumer (bfs_traversal,
        # traversal_selector.py) keeps working unchanged; only a caller
        # that explicitly wants metadata (trace_impact.py) looks here.
        self.edge_metadata: Dict[tuple[str, str, str], dict] = {}

    def add_node(self, node: Node):
        self.nodes[node.canonical_id] = node

    def add_edge(
        self,
        from_cid: str,
        to_cid: str,
        relation_type: str,
        metadata: dict | None = None,
    ):
        from_node = self.nodes.get(from_cid)
        to_node = self.nodes.get(to_cid)
        if not from_node or not to_node:
            raise ValueError(f"Cannot add edge: nodes missing {from_cid} -> {to_cid}")
        from_node.out_edges[relation_type].add(to_node)
        to_node.in_edges[relation_type].add(from_node)
        if metadata:
            self.edge_metadata[(from_cid, to_cid, relation_type)] = metadata

    def get_edge_metadata(
        self,
        from_cid: str,
        to_cid: str,
        relation_type: str,
    ) -> dict:
        """{} when no metadata was ever recorded for this directed edge --
        never raises, so callers can look this up unconditionally."""
        return self.edge_metadata.get((from_cid, to_cid, relation_type), {})

    def get_node(self, canonical_id: str) -> Optional[Node]:
        return self.nodes.get(canonical_id)


# --- Traversal Functions ---


def bfs_traversal(
    graph: CodebaseGraph,
    start_cid: str,
    relation_types: Optional[Set[str]] = None,
    direction: str = "forward",
    max_depth: int = 3,
) -> List[Node]:
    """
    Breadth-first traversal of graph starting from a node.
    """
    start_node = graph.get_node(start_cid)
    if not start_node:
        return []

    visited: Set[str] = set()
    queue: deque = deque([(start_node, 0)])
    results: List[Node] = []

    while queue:
        current_node, depth = queue.popleft()
        if current_node.canonical_id in visited:
            continue
        visited.add(current_node.canonical_id)

        if depth > 0:
            results.append(current_node)

        if depth >= max_depth:
            continue

        # Choose edges based on direction
        edges = (
            current_node.out_edges if direction == "forward" else current_node.in_edges
        )

        for rel, neighbors in edges.items():
            if relation_types and rel not in relation_types:
                continue
            for neighbor in neighbors:
                if neighbor.canonical_id not in visited:
                    queue.append((neighbor, depth + 1))

    return results


# -------------------------------
# Convenience Traversals
# -------------------------------


def traverse_calls(graph: CodebaseGraph, start_cid: str, depth: int = 3) -> List[Node]:
    """Traverse CALL edges forward (what does this node call?)."""
    return bfs_traversal(
        graph, start_cid, relation_types={"CALL"}, direction="forward", max_depth=depth
    )


def traverse_defines(
    graph: CodebaseGraph, start_cid: str, depth: int = 3
) -> List[Node]:
    """Traverse DEFINES edges forward (what does this node define?)."""
    return bfs_traversal(
        graph,
        start_cid,
        relation_types={"DEFINES"},
        direction="forward",
        max_depth=depth,
    )


def traverse_incoming_calls(
    graph: CodebaseGraph, start_cid: str, depth: int = 3
) -> List[Node]:
    """Traverse CALL edges in reverse (what calls this node?)."""
    return bfs_traversal(
        graph, start_cid, relation_types={"CALL"}, direction="reverse", max_depth=depth
    )


def traverse_incoming_imports(
    graph: CodebaseGraph, start_cid: str, depth: int = 3
) -> List[Node]:
    """Traverse IMPORTS edges in reverse (what imports this node?).

    F-02: ingestion now materializes MODULE --IMPORTS--> MODULE edges
    (relation_type "IMPORTS"); the old "IMPORT" type never existed as an
    edge, so this traversal used to return nothing.
    """
    return bfs_traversal(
        graph,
        start_cid,
        relation_types={"IMPORTS"},
        direction="reverse",
        max_depth=depth,
    )


# WP-G6: traversals over the WP-G5 inheritance edges.


def traverse_superclasses(
    graph: CodebaseGraph, start_cid: str, depth: int = 3
) -> List[Node]:
    """Traverse INHERITS edges forward (what does this class inherit from?)."""
    return bfs_traversal(
        graph,
        start_cid,
        relation_types={"INHERITS"},
        direction="forward",
        max_depth=depth,
    )


def traverse_subclasses(
    graph: CodebaseGraph, start_cid: str, depth: int = 3
) -> List[Node]:
    """Traverse INHERITS edges in reverse (what subclasses this class?)."""
    return bfs_traversal(
        graph,
        start_cid,
        relation_types={"INHERITS"},
        direction="reverse",
        max_depth=depth,
    )


def traverse_overrides(
    graph: CodebaseGraph, start_cid: str, depth: int = 3
) -> List[Node]:
    """Traverse OVERRIDES edges forward (which base method does this override?)."""
    return bfs_traversal(
        graph,
        start_cid,
        relation_types={"OVERRIDES"},
        direction="forward",
        max_depth=depth,
    )


def traverse_overridden_by(
    graph: CodebaseGraph, start_cid: str, depth: int = 3
) -> List[Node]:
    """Traverse OVERRIDES edges in reverse (which methods override this one?)."""
    return bfs_traversal(
        graph,
        start_cid,
        relation_types={"OVERRIDES"},
        direction="reverse",
        max_depth=depth,
    )


# --- API Calls ---


def get_nodes_by_canonical_ids_from_api(
    repo_id: str, canonical_ids: List[str]
) -> List[Dict]:
    """
    Fetch nodes by canonical_ids from the ingestion_service API
    (instead of directly querying DB).
    """
    # url = f"http://ingestion_service/v1/graph/repos/{repo_id}/nodes"
    url = f"{ingestion_service_url}/v1/graph/repos/{repo_id}/nodes"
    params = {"canonical_ids": ",".join(canonical_ids)}
    response = requests.get(url, params=params)

    if response.status_code == 200:
        return response.json().get("nodes", [])
    else:
        raise Exception(
            f"Error fetching nodes: {response.status_code} - {response.text}"
        )


class GraphSnapshotError(HTTPException):
    """Explicit unavailable/conflict/protocol outcome, never source absence."""


def get_repo_generation(repo_id: str) -> tuple[Optional[str], str]:
    """Cheap coherent lookup. Untrusted/failed lookups cannot authorize a hit."""
    url = f"{ingestion_service_url}/v1/repos/{repo_id}/generation"
    try:
        response = requests.get(url, timeout=5)
        if response.status_code != 200:
            return None, "unknown"
        body = response.json()
        if not isinstance(body, dict) or body.get("repo_id") != repo_id:
            return None, "unknown"
        status = body.get("generation_status")
        identity = body.get("ingestion_id")
        if status == "ready" and isinstance(identity, str):
            return str(UUID(identity)), "ready"
        if status in ("building", "failed", "unknown") and identity is None:
            return None, status
    except (requests.RequestException, ValueError, TypeError):
        logger.warning("Generation check failed for %s", repo_id, exc_info=True)
    return None, "unknown"


def get_full_graph_from_api(
    repo_id: str,
    expected_generation_id: Optional[str] = None,
) -> Dict:
    url = f"{ingestion_service_url}/v1/graph/repos/{repo_id}"
    params = (
        {"expected_generation_id": expected_generation_id}
        if expected_generation_id is not None
        else {}
    )
    try:
        response = requests.get(url, params=params, timeout=(5, 70))
        if response.status_code == 409:
            raise GraphSnapshotError(409, "Repository generation changed; retry")
        if response.status_code != 200:
            raise GraphSnapshotError(503, "Repository graph export unavailable")
        return response.json()
    except (requests.RequestException, ValueError) as exc:
        raise GraphSnapshotError(503, "Repository graph export unavailable") from exc


def _invalid_graph() -> NoReturn:
    raise GraphSnapshotError(502, "Invalid repository graph snapshot envelope")


def _validate_nodes(nodes) -> set[str]:
    if not isinstance(nodes, list) or not nodes:
        _invalid_graph()
    cids, document_ids = set(), set()
    fields = ("canonical_id", "document_id", "relative_path", "title", "doc_type")
    for node in nodes:
        if not isinstance(node, dict):
            _invalid_graph()
        if any(not isinstance(node.get(field), str) for field in fields):
            _invalid_graph()
        cid, doc_id = node["canonical_id"], node["document_id"]
        if not cid or not doc_id or cid in cids or doc_id in document_ids:
            _invalid_graph()
        if node.get("provenance") is not None and not isinstance(
            node["provenance"], dict
        ):
            _invalid_graph()
        cids.add(cid)
        document_ids.add(doc_id)
    return cids


def _validate_relationships(relationships, cids: set[str]) -> None:
    if not isinstance(relationships, dict):
        _invalid_graph()
    for source, edges in relationships.items():
        if source not in cids or not isinstance(edges, list):
            _invalid_graph()
        for edge in edges:
            if not isinstance(edge, dict):
                _invalid_graph()
            target, relation = edge.get("to_canonical_id"), edge.get("relation_type")
            if (
                not isinstance(target, str)
                or target not in cids
                or not isinstance(relation, str)
                or not relation
                or not isinstance(edge.get("relationship_metadata"), dict)
            ):
                _invalid_graph()


def _validate_graph_snapshot(data: Dict, repo_id: str, expected: Optional[str]) -> str:
    """Validate before constructing a graph or discarding metadata."""
    if not isinstance(data, dict) or data.get("repo_id") != repo_id:
        _invalid_graph()
    status = data.get("generation_status")
    if status in ("building", "failed", "unknown"):
        raise GraphSnapshotError(503, f"Repository graph unavailable ({status})")
    if status != "ready" or not isinstance(data.get("ingestion_id"), str):
        _invalid_graph()
    try:
        generation = str(UUID(data["ingestion_id"]))
    except (ValueError, TypeError, AttributeError):
        _invalid_graph()
    if expected is not None and generation != expected:
        raise GraphSnapshotError(409, "Repository graph identity changed; retry")
    cids = _validate_nodes(data.get("nodes"))
    if type(data.get("total_nodes")) is not int or data["total_nodes"] != len(cids):
        _invalid_graph()
    _validate_relationships(data.get("relationships"), cids)
    return generation


def load_graph_for_repo(
    repo_id: str,
    expected_generation_id: Optional[str] = None,
) -> CodebaseGraph:
    data = get_full_graph_from_api(repo_id, expected_generation_id)
    generation = _validate_graph_snapshot(data, repo_id, expected_generation_id)
    graph = CodebaseGraph()
    graph.repo_id, graph.ingestion_id = repo_id, generation
    for node in data["nodes"]:
        graph.add_node(
            Node(
                canonical_id=node["canonical_id"],
                file_path=node["relative_path"],
                provenance=node.get("provenance"),
            )
        )
    for from_cid, edges in data["relationships"].items():
        for edge in edges:
            graph.add_edge(
                from_cid,
                edge["to_canonical_id"],
                edge["relation_type"],
                metadata=edge["relationship_metadata"],
            )
    return graph
