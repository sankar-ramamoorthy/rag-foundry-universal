from collections import deque, defaultdict
from typing import List, Set, Dict, Optional
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


def get_repo_generation(repo_id: str) -> tuple[Optional[str], str]:
    """
    #168 (WP-R5): cheap check of repo_id's current servable generation --
    does not fetch nodes/relationships, only ingestion_service's
    db_utils.resolve_current_generation/generation_status lookup (#166).
    Used by the graph cache to detect a rebuild without paying for a full
    graph re-fetch on every request.

    Returns (ingestion_id, generation_status). ingestion_id is None unless
    generation_status is "ready". A non-200 response (repo_id truly
    unknown to this call, or a transient error) is treated the same as
    "unknown" -- callers must not raise the whole retrieval request over a
    freshness-check failure; graph expansion degrading to empty is
    preferable to a hard failure on the vector-seed half of the answer.
    """
    url = f"{ingestion_service_url}/v1/repos/{repo_id}/generation"
    try:
        response = requests.get(url, timeout=5)
    except requests.RequestException:
        logger.warning(
            f"Generation check failed for repo_id={repo_id[:8]}",
            exc_info=True,
        )
        return None, "unknown"

    if response.status_code != 200:
        logger.warning(
            f"Generation check for repo_id={repo_id[:8]} returned "
            f"{response.status_code}: {response.text}"
        )
        return None, "unknown"

    body = response.json()
    return body.get("ingestion_id"), body.get("generation_status", "unknown")


def get_full_graph_from_api(repo_id: str) -> Dict:
    """
    Fetch the full graph (nodes and relationships) for a given repository
    from the ingestion_service API.
    """
    # url = f"http://ingestion_service/v1/graph/repos/{repo_id}"
    url = f"{ingestion_service_url}/v1/graph/repos/{repo_id}"
    response = requests.get(url)

    if response.status_code == 200:
        return response.json()  # returns both nodes and edges
    else:
        raise Exception(
            f"Error fetching full graph: {response.status_code} - {response.text}"
        )


# --- Graph Loading ---


def load_graph_for_repo(repo_id: str) -> CodebaseGraph:
    """
    Build an in-memory CodebaseGraph from the ingestion_service API.
    """
    graph = CodebaseGraph()

    graph_data = get_full_graph_from_api(repo_id)

    # Step 1: Load Nodes
    # API returns nodes as a LIST of GraphNode dicts (not a dict keyed by canonical_id)
    for node in graph_data.get("nodes", []):
        new_node = Node(
            canonical_id=node["canonical_id"],
            file_path=node.get("relative_path"),
            lineno=node.get("lineno"),
            provenance=node.get("provenance"),
        )
        graph.add_node(new_node)

    # Step 2: Load Relationships
    # relationships is dict: from_canonical_id → [{to_canonical_id, relation_type}]
    for from_cid, edges in graph_data.get("relationships", {}).items():
        for edge in edges:
            to_cid = edge.get("to_canonical_id")
            relation_type = edge.get("relation_type")
            if from_cid in graph.nodes and to_cid in graph.nodes:
                # Issue #220: relationship_metadata now survives the
                # export -- pass it through so trace_impact.py can surface
                # confidence/call-site evidence per hop.
                graph.add_edge(
                    from_cid,
                    to_cid,
                    relation_type,
                    metadata=edge.get("relationship_metadata"),
                )

    logger.info(f"Graph built: {len(graph.nodes)} nodes")
    return graph
