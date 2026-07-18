# rag_orchestrator/tests/test_imports_traversal.py
"""
F-02: `traverse_incoming_imports` must traverse the IMPORTS edges that
ingestion now materializes (the old "IMPORT" relation type never existed
as an edge, so the traversal silently returned nothing).
"""
import pytest

from src.retrieval.codebase_queries import (
    CodebaseGraph,
    Node,
    traverse_incoming_imports,
)

pytestmark = pytest.mark.unit


def _graph_with_imports():
    graph = CodebaseGraph()
    for cid in ("app.py", "other.py", "pkg/util.py"):
        graph.add_node(Node(canonical_id=cid, file_path=cid))
    graph.add_edge("app.py", "pkg/util.py", "IMPORTS")
    graph.add_edge("other.py", "pkg/util.py", "IMPORTS")
    return graph


def test_incoming_imports_returns_importers():
    graph = _graph_with_imports()
    importers = {
        n.canonical_id
        for n in traverse_incoming_imports(graph, "pkg/util.py", depth=1)
    }
    assert importers == {"app.py", "other.py"}


def test_incoming_imports_ignores_other_edge_types():
    graph = _graph_with_imports()
    graph.add_node(Node(canonical_id="caller.py#f", file_path="caller.py"))
    graph.add_edge("caller.py#f", "pkg/util.py", "CALL")

    importers = {
        n.canonical_id
        for n in traverse_incoming_imports(graph, "pkg/util.py", depth=1)
    }
    assert "caller.py#f" not in importers
