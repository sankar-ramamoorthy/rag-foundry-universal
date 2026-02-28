from collections import deque, defaultdict
from typing import List, Set, Dict, Optional
import requests  # New import to call the ingestion service API
from src.core.config import get_settings 
import logging 

# Set up logging configuration
logging.basicConfig(level=logging.DEBUG)
logger = logging.getLogger(__name__)

settings = get_settings()
ingestion_service_url=settings.INGESTION_SERVICE_URL
# --- Graph Classes ---
class Node:
    """
    Represents a single artifact node in the graph.
    """
    def __init__(self, canonical_id: str, file_path: str, lineno: Optional[int] = None):
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
            raise ValueError(f"Cannot add edge: nodes missing {from_cid} -> {to_cid}")
        from_node.out_edges[relation_type].add(to_node)
        to_node.in_edges[relation_type].add(from_node)

    def get_node(self, canonical_id: str) -> Optional[Node]:
        return self.nodes.get(canonical_id)

# --- Traversal Functions ---

def bfs_traversal(
    graph: CodebaseGraph,
    start_cid: str,
    relation_types: Optional[Set[str]] = None,
    direction: str = "forward",
    max_depth: int = 3
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
        edges = current_node.out_edges if direction == "forward" else current_node.in_edges

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
    return bfs_traversal(graph, start_cid, relation_types={"CALL"}, direction="forward", max_depth=depth)


def traverse_defines(graph: CodebaseGraph, start_cid: str, depth: int = 3) -> List[Node]:
    """Traverse DEFINES edges forward (what does this node define?)."""
    return bfs_traversal(graph, start_cid, relation_types={"DEFINES"}, direction="forward", max_depth=depth)


def traverse_incoming_calls(graph: CodebaseGraph, start_cid: str, depth: int = 3) -> List[Node]:
    """Traverse CALL edges in reverse (what calls this node?)."""
    return bfs_traversal(graph, start_cid, relation_types={"CALL"}, direction="reverse", max_depth=depth)


def traverse_incoming_imports(graph: CodebaseGraph, start_cid: str, depth: int = 3) -> List[Node]:
    """Traverse IMPORT edges in reverse (what imports this node?)."""
    return bfs_traversal(graph, start_cid, relation_types={"IMPORT"}, direction="reverse", max_depth=depth)

# --- API Calls ---

def get_nodes_by_canonical_ids_from_api(repo_id: str, canonical_ids: List[str]) -> List[Dict]:
    """
    Fetch nodes by canonical_ids from the ingestion_service API (instead of directly querying DB).
    """
    #url = f"http://ingestion_service/v1/graph/repos/{repo_id}/nodes"
    url = f"{ingestion_service_url}/v1/graph/repos/{repo_id}/nodes"
    params = {"canonical_ids": ",".join(canonical_ids)}
    response = requests.get(url, params=params)

    if response.status_code == 200:
        return response.json().get('nodes', [])
    else:
        raise Exception(f"Error fetching nodes: {response.status_code} - {response.text}")


def get_full_graph_from_api(repo_id: str) -> Dict:
    """
    Fetch the full graph (nodes and relationships) for a given repository
    from the ingestion_service API.
    """
    #url = f"http://ingestion_service/v1/graph/repos/{repo_id}"
    url = f"{ingestion_service_url}/v1/graph/repos/{repo_id}"
    response = requests.get(url)

    if response.status_code == 200:
        return response.json()  # returns both nodes and edges
    else:
        raise Exception(f"Error fetching full graph: {response.status_code} - {response.text}")
    

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
        )
        graph.add_node(new_node)

    # Step 2: Load Relationships
    # relationships is dict: from_canonical_id → [{to_canonical_id, relation_type}]
    for from_cid, edges in graph_data.get("relationships", {}).items():
        for edge in edges:
            to_cid = edge.get("to_canonical_id")
            relation_type = edge.get("relation_type")
            if from_cid in graph.nodes and to_cid in graph.nodes:
                graph.add_edge(from_cid, to_cid, relation_type)

    logger.info(f"Graph built: {len(graph.nodes)} nodes")
    return graph