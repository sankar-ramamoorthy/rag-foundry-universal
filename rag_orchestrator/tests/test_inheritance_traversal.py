# rag_orchestrator/tests/test_inheritance_traversal.py
"""
WP-G6: the traversal layer exploits the WP-G5 INHERITS/OVERRIDES edges.
"""
import pytest

from src.retrieval.codebase_queries import (
    CodebaseGraph,
    Node,
    traverse_overridden_by,
    traverse_overrides,
    traverse_subclasses,
    traverse_superclasses,
)
from src.retrieval.traversal_selector import (
    execute_traversals_from_seeds,
    select_traversal_strategies,
)

pytestmark = pytest.mark.unit


@pytest.fixture()
def graph():
    """Calculator <- Scientific <- Graphing hierarchy, plus one override."""
    g = CodebaseGraph()
    for cid in [
        "calc.py#Calculator",
        "sci.py#Scientific",
        "graph.py#Graphing",
        "calc.py#Calculator.compute",
        "sci.py#Scientific.compute",
    ]:
        g.add_node(Node(cid, cid.split("#")[0]))

    g.add_edge("sci.py#Scientific", "calc.py#Calculator", "INHERITS")
    g.add_edge("graph.py#Graphing", "sci.py#Scientific", "INHERITS")
    g.add_edge(
        "sci.py#Scientific.compute", "calc.py#Calculator.compute", "OVERRIDES"
    )
    return g


def cids(nodes):
    return {n.canonical_id for n in nodes}


def test_traverse_subclasses_walks_reverse_inherits(graph):
    assert cids(traverse_subclasses(graph, "calc.py#Calculator", depth=2)) == {
        "sci.py#Scientific",
        "graph.py#Graphing",
    }


def test_traverse_superclasses_walks_forward_inherits(graph):
    assert cids(traverse_superclasses(graph, "graph.py#Graphing", depth=2)) == {
        "sci.py#Scientific",
        "calc.py#Calculator",
    }


def test_traverse_overrides_and_reverse(graph):
    assert cids(
        traverse_overrides(graph, "sci.py#Scientific.compute", depth=1)
    ) == {"calc.py#Calculator.compute"}
    assert cids(
        traverse_overridden_by(graph, "calc.py#Calculator.compute", depth=1)
    ) == {"sci.py#Scientific.compute"}


def test_what_subclasses_calculator_end_to_end(graph):
    """WP-G6 acceptance: 'what subclasses Calculator' returns subclass
    nodes when expanded from the Calculator seed."""
    seeds = {"calc.py#Calculator"}
    strategies = select_traversal_strategies("what subclasses Calculator", seeds)
    nodes = execute_traversals_from_seeds(graph, seeds, strategies)
    assert "sci.py#Scientific" in cids(nodes)
