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


@pytest.fixture()
def graph_with_modules():
    """Same hierarchy as `graph`, but with MODULE nodes DEFINES-linked to
    their classes/methods — mirrors the real ingested graph shape, where
    INHERITS/OVERRIDES edges live on CLASS/METHOD nodes while vector
    search often seeds the coarser MODULE artifact instead (issue #48)."""
    g = CodebaseGraph()
    for cid, path in [
        ("calc.py", "calc.py"),
        ("calc.py#Calculator", "calc.py"),
        ("calc.py#Calculator.compute", "calc.py"),
        ("sci.py", "sci.py"),
        ("sci.py#Scientific", "sci.py"),
        ("sci.py#Scientific.compute", "sci.py"),
    ]:
        g.add_node(Node(cid, path))

    g.add_edge("calc.py", "calc.py#Calculator", "DEFINES")
    g.add_edge("calc.py#Calculator", "calc.py#Calculator.compute", "DEFINES")
    g.add_edge("sci.py", "sci.py#Scientific", "DEFINES")
    g.add_edge("sci.py#Scientific", "sci.py#Scientific.compute", "DEFINES")
    g.add_edge("sci.py#Scientific", "calc.py#Calculator", "INHERITS")
    g.add_edge(
        "sci.py#Scientific.compute", "calc.py#Calculator.compute", "OVERRIDES"
    )
    return g


def test_module_level_seed_still_finds_subclasses(graph_with_modules):
    """issue #48 regression: at low top_k, vector search can seed the
    MODULE (calc.py) rather than the CLASS (calc.py#Calculator). Before
    the fix, traversal ran BFS from calc.py itself, which has no INHERITS
    edge, so 'what subclasses Calculator' silently returned nothing even
    though sci.py#Scientific inherits from it."""
    seeds = {"calc.py"}
    strategies = select_traversal_strategies("what subclasses Calculator", seeds)
    nodes = execute_traversals_from_seeds(graph_with_modules, seeds, strategies)
    assert "sci.py#Scientific" in cids(nodes)


def test_class_level_seed_still_finds_method_overrides(graph_with_modules):
    """Same gap one level down: seeding the CLASS (sci.py#Scientific)
    rather than the METHOD (sci.py#Scientific.compute) must still surface
    the OVERRIDES edge that lives on the method."""
    seeds = {"sci.py#Scientific"}
    strategies = select_traversal_strategies(
        "which methods are overridden in Scientific", seeds
    )
    nodes = execute_traversals_from_seeds(graph_with_modules, seeds, strategies)
    assert "calc.py#Calculator.compute" in cids(nodes)


def test_module_seed_structure_query_unaffected(graph_with_modules):
    """The anchor expansion must not make a seed's own DEFINES children
    disappear from a 'structure' query's results — those children ARE
    the expected answer for 'what does calc.py define'."""
    seeds = {"calc.py"}
    strategies = select_traversal_strategies("what classes are defined in calc.py", seeds)
    nodes = execute_traversals_from_seeds(graph_with_modules, seeds, strategies)
    assert "calc.py#Calculator" in cids(nodes)
