# rag_orchestrator/tests/test_mentioned_method_discovery.py
"""
Issue #257: a class that reaches the expanded-candidate set only through a
*different* seed's non-DEFINES expansion never had its own DEFINES
children explored, even when the query explicitly names one of them and
the graph already has the edge (confirmed for #254: `agent.py#Agent`
reached `expanded_canonical_ids`, but `agent.py#Agent.run` never did).
"""
from dataclasses import dataclass

import pytest

from src.retrieval.codebase_queries import CodebaseGraph, Node, traverse_calls
from src.retrieval.traversal_selector import (
    ExpandedCandidate,
    execute_traversals_from_seeds_detailed,
    expand_mentioned_methods,
)

pytestmark = pytest.mark.unit


@dataclass(frozen=True)
class FakeNode:
    canonical_id: str


def _candidate(cid: str, strategy_index: int = 0) -> ExpandedCandidate:
    return ExpandedCandidate(
        node=FakeNode(cid),
        strategy_index=strategy_index,
        relation_type="CALL",
        source_seed_canonical_id="seed.py#Seed",
    )


def test_discovers_explicitly_mentioned_method_from_non_seed_class():
    """`Agent` reaches the candidate set via CALL from a different seed;
    the query names `Agent.run`; the DEFINES edge to it exists -- it
    should now be admitted."""
    g = CodebaseGraph()
    for cid in ["agent.py#Agent", "agent.py#Agent.run", "agent.py#Agent.stop"]:
        g.add_node(Node(cid, "agent.py"))
    g.add_edge("agent.py#Agent", "agent.py#Agent.run", "DEFINES")
    g.add_edge("agent.py#Agent", "agent.py#Agent.stop", "DEFINES")

    candidates = [_candidate("agent.py#Agent")]
    extra = expand_mentioned_methods(
        g, "trace `Agent.run` to the next LLM call", candidates,
        seed_canonical_ids={"other.py#Seed"},
    )

    assert [c.node.canonical_id for c in extra] == ["agent.py#Agent.run"]
    assert extra[0].relation_type == "DEFINES"
    assert extra[0].source_seed_canonical_id == "agent.py#Agent"
    assert extra[0].strategy_index == -1


def test_does_not_flood_unrelated_class_with_same_named_method():
    """Negative control: a *different*, unrelated class also defines a
    `run` method. Naming `Agent.run` must not pull in `Worker.run` just
    because the method name matches."""
    g = CodebaseGraph()
    for cid in [
        "agent.py#Agent", "agent.py#Agent.run",
        "worker.py#Worker", "worker.py#Worker.run",
    ]:
        g.add_node(Node(cid, cid.split("#")[0]))
    g.add_edge("agent.py#Agent", "agent.py#Agent.run", "DEFINES")
    g.add_edge("worker.py#Worker", "worker.py#Worker.run", "DEFINES")

    # Both classes are already candidates (e.g. via unrelated CALL edges).
    candidates = [_candidate("agent.py#Agent"), _candidate("worker.py#Worker")]
    extra = expand_mentioned_methods(
        g, "trace `Agent.run` to the next LLM call", candidates,
        seed_canonical_ids=set(),
    )

    assert [c.node.canonical_id for c in extra] == ["agent.py#Agent.run"]


def test_unmentioned_class_not_touched_even_if_candidate():
    """A candidate class whose name the query never mentions is left
    alone -- no blanket re-expansion of every candidate class."""
    g = CodebaseGraph()
    for cid in ["agent.py#Agent", "agent.py#Agent.run"]:
        g.add_node(Node(cid, "agent.py"))
    g.add_edge("agent.py#Agent", "agent.py#Agent.run", "DEFINES")

    candidates = [_candidate("agent.py#Agent")]
    extra = expand_mentioned_methods(
        g, "what does the provider registry do?", candidates,
        seed_canonical_ids=set(),
    )

    assert extra == []


def test_no_match_when_query_mentions_nothing_preserves_existing_behavior():
    g = CodebaseGraph()
    g.add_node(Node("agent.py#Agent", "agent.py"))
    extra = expand_mentioned_methods(
        g, "", [_candidate("agent.py#Agent")], seed_canonical_ids=set(),
    )
    assert extra == []


def test_class_that_is_itself_a_seed_is_skipped():
    """Already covered by `_seed_and_defines_descendants` -- avoid a
    duplicate candidate for the same method via a second path."""
    g = CodebaseGraph()
    for cid in ["agent.py#Agent", "agent.py#Agent.run"]:
        g.add_node(Node(cid, "agent.py"))
    g.add_edge("agent.py#Agent", "agent.py#Agent.run", "DEFINES")

    candidates = [_candidate("agent.py#Agent")]
    extra = expand_mentioned_methods(
        g, "trace `Agent.run`", candidates,
        seed_canonical_ids={"agent.py#Agent"},
    )
    assert extra == []


def test_already_present_method_is_not_duplicated():
    g = CodebaseGraph()
    for cid in ["agent.py#Agent", "agent.py#Agent.run"]:
        g.add_node(Node(cid, "agent.py"))
    g.add_edge("agent.py#Agent", "agent.py#Agent.run", "DEFINES")

    candidates = [_candidate("agent.py#Agent"), _candidate("agent.py#Agent.run")]
    extra = expand_mentioned_methods(
        g, "trace `Agent.run`", candidates, seed_canonical_ids=set(),
    )
    assert extra == []


def test_method_candidate_is_not_used_as_a_class_anchor():
    """A method already in `candidates` (fragment has a '.') must not be
    treated as a class to re-expand from."""
    g = CodebaseGraph()
    for cid in ["agent.py#Agent.run", "agent.py#Agent.run.nested"]:
        g.add_node(Node(cid, "agent.py"))
    g.add_edge("agent.py#Agent.run", "agent.py#Agent.run.nested", "DEFINES")

    candidates = [_candidate("agent.py#Agent.run")]
    extra = expand_mentioned_methods(
        g, "trace `Agent.run`", candidates, seed_canonical_ids=set(),
    )
    assert extra == []


def test_end_to_end_with_real_call_edge_expansion():
    """Full shape of the #254 scenario: Agent is discovered via CALL from
    a different seed (not DEFINES, not itself a seed), then the explicit
    mention recovers Agent.run on top of the ordinary expansion."""
    g = CodebaseGraph()
    for cid in [
        "caller.py#Caller", "caller.py#Caller.dispatch",
        "agent.py#Agent", "agent.py#Agent.run",
    ]:
        g.add_node(Node(cid, cid.split("#")[0]))
    g.add_edge("caller.py#Caller.dispatch", "agent.py#Agent", "CALL")
    g.add_edge("agent.py#Agent", "agent.py#Agent.run", "DEFINES")

    seeds = {"caller.py#Caller.dispatch"}
    candidates = execute_traversals_from_seeds_detailed(
        g, seeds, [lambda graph, cid: traverse_calls(graph, cid, depth=1)]
    )
    assert "agent.py#Agent" in {c.node.canonical_id for c in candidates}
    assert "agent.py#Agent.run" not in {c.node.canonical_id for c in candidates}

    extra = expand_mentioned_methods(
        g, "trace `Agent.run`", candidates, seed_canonical_ids=seeds,
    )
    assert [c.node.canonical_id for c in extra] == ["agent.py#Agent.run"]
