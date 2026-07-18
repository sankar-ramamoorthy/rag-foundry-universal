# rag_orchestrator/tests/test_multi_seed_traversal.py
"""
F-12: graph expansion must traverse from ALL seed canonical_ids.

Before the fix, only the longest seed string was expanded
(`max(seed_canonical_ids, key=len)`) and every other vector-search hit
was silently dropped from graph expansion.
"""
from dataclasses import dataclass

import pytest

from src.retrieval.traversal_selector import execute_traversals_from_seeds

pytestmark = pytest.mark.unit


@dataclass(frozen=True)
class FakeNode:
    canonical_id: str


def children_of(graph, start_cid):
    """Stub strategy: each seed expands to one child node."""
    return [FakeNode(canonical_id=f"{start_cid}:child")]


def test_all_seeds_are_expanded():
    seeds = {"a.py#f", "lib/very_long_name.py#Klass.method", "b.py#g"}

    nodes = execute_traversals_from_seeds(
        graph=None, seed_canonical_ids=seeds, strategies=[children_of]
    )

    expanded = {n.canonical_id for n in nodes}
    # the old single-seed behavior would only contain the longest seed's child
    assert expanded == {
        "a.py#f:child",
        "lib/very_long_name.py#Klass.method:child",
        "b.py#g:child",
    }


def test_nodes_deduplicated_across_seeds():
    def same_child(graph, start_cid):
        return [FakeNode(canonical_id="shared:node")]

    nodes = execute_traversals_from_seeds(
        graph=None,
        seed_canonical_ids={"a.py#f", "b.py#g"},
        strategies=[same_child],
    )
    assert [n.canonical_id for n in nodes] == ["shared:node"]


def test_seed_iteration_is_deterministic():
    seeds = {"z.py#f", "a.py#f", "m.py#f"}
    calls = []

    def recording(graph, start_cid):
        calls.append(start_cid)
        return []

    execute_traversals_from_seeds(
        graph=None, seed_canonical_ids=seeds, strategies=[recording]
    )
    assert calls == sorted(seeds)


def test_failing_strategy_does_not_abort_other_seeds():
    def flaky(graph, start_cid):
        if start_cid == "bad.py#f":
            raise RuntimeError("boom")
        return [FakeNode(canonical_id=f"{start_cid}:child")]

    nodes = execute_traversals_from_seeds(
        graph=None,
        seed_canonical_ids={"bad.py#f", "good.py#f"},
        strategies=[flaky],
    )
    assert {n.canonical_id for n in nodes} == {"good.py#f:child"}


def test_no_seeds_returns_empty():
    assert execute_traversals_from_seeds(
        graph=None, seed_canonical_ids=set(), strategies=[children_of]
    ) == []
