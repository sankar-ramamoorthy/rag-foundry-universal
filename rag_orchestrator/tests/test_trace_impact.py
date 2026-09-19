# rag_orchestrator/tests/test_trace_impact.py
"""
Issue #198: pure function tests for TRACE/IMPACT's bounded graph
traversal -- no DB/HTTP, small hand-built CodebaseGraph fixtures.
"""

import pytest

from src.retrieval.codebase_queries import CodebaseGraph, Node
from src.retrieval.trace_impact import (
    AmbiguousStart,
    ResolvedStart,
    assess_impact,
    resolve_start_symbol,
    traced_path,
)

pytestmark = pytest.mark.unit


def _graph(
    edges: list[tuple[str, str, str]], extra_nodes: list[str] | None = None
) -> CodebaseGraph:
    """Build a CodebaseGraph from (from_cid, to_cid, relation_type) triples.
    Every canonical_id mentioned gets a Node with file_path derived from
    the part before '#' (or itself for file-level ids)."""
    graph = CodebaseGraph()
    all_cids = {cid for edge in edges for cid in (edge[0], edge[1])}
    all_cids |= set(extra_nodes or [])
    for cid in all_cids:
        file_path = cid.split("#", 1)[0]
        graph.add_node(Node(canonical_id=cid, file_path=file_path))
    for from_cid, to_cid, relation_type in edges:
        graph.add_edge(from_cid, to_cid, relation_type)
    return graph


# --- resolve_start_symbol ---


def test_resolve_exact_canonical_id():
    graph = _graph([("a.py#foo", "a.py#bar", "CALL")])
    resolved = resolve_start_symbol(graph, "a.py#foo")
    assert resolved == ResolvedStart(canonical_id="a.py#foo", file_path="a.py")


def test_resolve_unambiguous_bare_symbol():
    graph = _graph([("a.py#foo", "a.py#bar", "CALL")])
    resolved = resolve_start_symbol(graph, "foo")
    assert resolved == ResolvedStart(canonical_id="a.py#foo", file_path="a.py")


def test_resolve_unambiguous_bare_symbol_dotted_suffix_match():
    graph = _graph([("a.py#Widget.run", "a.py#helper", "CALL")])
    resolved = resolve_start_symbol(graph, "run")
    assert resolved == ResolvedStart(canonical_id="a.py#Widget.run", file_path="a.py")


def test_resolve_ambiguous_bare_symbol_reports_every_candidate_no_silent_pick():
    graph = _graph(
        [
            ("service_a.py#run", "service_a.py#helper", "CALL"),
            ("service_b.py#run", "service_b.py#helper", "CALL"),
            ("worker.py#run", "worker.py#helper", "CALL"),
        ]
    )
    resolved = resolve_start_symbol(graph, "run")
    assert isinstance(resolved, AmbiguousStart)
    assert resolved.query == "run"
    assert resolved.candidates == [
        "service_a.py#run",
        "service_b.py#run",
        "worker.py#run",
    ]


def test_resolve_no_match_returns_none():
    graph = _graph([("a.py#foo", "a.py#bar", "CALL")])
    assert resolve_start_symbol(graph, "nonexistent") is None


# --- traced_path ---


def test_traced_path_linear_chain_ordered_hops():
    graph = _graph(
        [
            ("a.py#foo", "b.py#bar", "CALL"),
            ("b.py#bar", "c.py#baz", "CALL"),
        ]
    )
    result = traced_path(
        graph,
        "a.py#foo",
        relation_types={"CALL"},
        direction="forward",
        max_depth=6,
        max_nodes=300,
    )
    assert not result.truncated
    assert [h.canonical_id for h in result.hops] == ["b.py#bar", "c.py#baz"]
    assert result.hops[0].hop_index == 1
    assert result.hops[0].relation_type == "CALL"
    assert result.hops[0].parent_canonical_id == "a.py#foo"
    assert result.hops[1].hop_index == 2
    assert result.hops[1].parent_canonical_id == "b.py#bar"


def test_traced_path_forward_hop_carries_edge_metadata():
    graph = CodebaseGraph()
    graph.add_node(Node(canonical_id="a.py#foo", file_path="a.py"))
    graph.add_node(Node(canonical_id="b.py#bar", file_path="b.py"))
    graph.add_edge(
        "a.py#foo",
        "b.py#bar",
        "CALL",
        metadata={"confidence": 1.0, "call_sites": [12], "count": 1},
    )

    result = traced_path(
        graph,
        "a.py#foo",
        relation_types={"CALL"},
        direction="forward",
        max_depth=6,
        max_nodes=300,
    )
    assert result.hops[0].metadata == {
        "confidence": 1.0,
        "call_sites": [12],
        "count": 1,
    }


def test_traced_path_reverse_hop_carries_edge_metadata_of_the_real_directed_edge():
    graph = CodebaseGraph()
    graph.add_node(Node(canonical_id="caller.py#outer", file_path="caller.py"))
    graph.add_node(Node(canonical_id="callee.py#inner", file_path="callee.py"))
    # the real edge is caller -> callee; metadata is keyed on that
    # direction regardless of which direction traced_path is later asked
    # to walk it.
    graph.add_edge(
        "caller.py#outer",
        "callee.py#inner",
        "CALL",
        metadata={"confidence": 0.5},
    )

    result = traced_path(
        graph,
        "callee.py#inner",
        relation_types={"CALL"},
        direction="reverse",
        max_depth=6,
        max_nodes=300,
    )
    assert result.hops[0].canonical_id == "caller.py#outer"
    assert result.hops[0].metadata == {"confidence": 0.5}


def test_traced_path_hop_metadata_defaults_to_empty_dict_when_none_recorded():
    graph = _graph([("a.py#foo", "b.py#bar", "CALL")])  # no metadata passed
    result = traced_path(
        graph,
        "a.py#foo",
        relation_types={"CALL"},
        direction="forward",
        max_depth=6,
        max_nodes=300,
    )
    assert result.hops[0].metadata == {}


def test_traced_path_branching_chain_deterministic_order():
    graph = _graph(
        [
            ("a.py#foo", "b.py#bar", "CALL"),
            ("a.py#foo", "c.py#baz", "CALL"),
        ]
    )
    result = traced_path(
        graph,
        "a.py#foo",
        relation_types={"CALL"},
        direction="forward",
        max_depth=6,
        max_nodes=300,
    )
    # sorted by canonical_id at each level -> deterministic order
    assert [h.canonical_id for h in result.hops] == ["b.py#bar", "c.py#baz"]


def test_traced_path_respects_max_depth():
    graph = _graph(
        [
            ("a.py#foo", "b.py#bar", "CALL"),
            ("b.py#bar", "c.py#baz", "CALL"),
        ]
    )
    result = traced_path(
        graph,
        "a.py#foo",
        relation_types={"CALL"},
        direction="forward",
        max_depth=1,
        max_nodes=300,
    )
    assert [h.canonical_id for h in result.hops] == ["b.py#bar"]
    assert not result.truncated  # depth bound, not node bound


def test_traced_path_max_nodes_stops_computation_not_just_output():
    # A wide fan-out: if max_nodes truncation still walked the whole
    # graph, this would be slow/wrong; instead it must stop the instant
    # the budget is hit and never enqueue further neighbors.
    edges = [("a.py#foo", f"n{i}.py#x", "CALL") for i in range(10)]
    graph = _graph(edges)
    result = traced_path(
        graph,
        "a.py#foo",
        relation_types={"CALL"},
        direction="forward",
        max_depth=6,
        max_nodes=3,
    )
    assert result.truncated
    assert len(result.hops) == 3


def test_traced_path_unfiltered_relation_types_when_none():
    graph = _graph(
        [
            ("a.py#foo", "a.py#bar", "DEFINES"),
            ("a.py#foo", "b.py#baz", "CALL"),
        ]
    )
    result = traced_path(
        graph,
        "a.py#foo",
        relation_types=None,
        direction="forward",
        max_depth=6,
        max_nodes=300,
    )
    assert {h.canonical_id for h in result.hops} == {"a.py#bar", "b.py#baz"}


def test_traced_path_external_symbol_is_a_hop_and_a_gap():
    graph = _graph(
        [("a.py#foo", "EXTERNAL_SYMBOL:requests.get", "CALL")],
    )
    result = traced_path(
        graph,
        "a.py#foo",
        relation_types={"CALL"},
        direction="forward",
        max_depth=6,
        max_nodes=300,
    )
    assert [h.canonical_id for h in result.hops] == ["EXTERNAL_SYMBOL:requests.get"]
    assert len(result.gaps) == 1
    assert result.gaps[0].canonical_id == "EXTERNAL_SYMBOL:requests.get"
    assert "cannot continue" in result.gaps[0].reason


def test_traced_path_reverse_direction():
    graph = _graph([("caller.py#outer", "callee.py#inner", "CALL")])
    result = traced_path(
        graph,
        "callee.py#inner",
        relation_types={"CALL"},
        direction="reverse",
        max_depth=6,
        max_nodes=300,
    )
    assert [h.canonical_id for h in result.hops] == ["caller.py#outer"]


def test_traced_path_unresolvable_start_raises():
    graph = _graph([("a.py#foo", "a.py#bar", "CALL")])
    with pytest.raises(KeyError):
        traced_path(
            graph,
            "nope.py#missing",
            relation_types={"CALL"},
            direction="forward",
            max_depth=6,
            max_nodes=300,
        )


# --- assess_impact ---


def test_assess_impact_candidate_with_multiple_bases():
    graph = _graph(
        [
            ("caller.py#outer", "target.py#fn", "CALL"),
            ("caller.py#outer", "target.py#fn", "IMPORTS"),
        ]
    )
    result = assess_impact(graph, "target.py#fn", max_depth=4, max_candidates=300)
    assert len(result.candidates) == 1
    candidate = result.candidates[0]
    assert candidate.canonical_id == "caller.py#outer"
    relation_types_found = {b.relation_type for b in candidate.basis}
    assert relation_types_found == {"CALL", "IMPORTS"}


def test_assess_impact_basis_carries_edge_metadata():
    graph = CodebaseGraph()
    graph.add_node(Node(canonical_id="caller.py#outer", file_path="caller.py"))
    graph.add_node(Node(canonical_id="target.py#fn", file_path="target.py"))
    graph.add_edge(
        "caller.py#outer",
        "target.py#fn",
        "CALL",
        metadata={"confidence": 1.0, "call_sites": [5]},
    )

    result = assess_impact(graph, "target.py#fn", max_depth=4, max_candidates=300)
    basis = result.candidates[0].basis[0]
    assert basis.metadata == {"confidence": 1.0, "call_sites": [5]}


def test_assess_impact_excludes_defines_and_documents():
    graph = _graph(
        [
            ("module.py", "module.py#fn", "DEFINES"),
            ("docs.md#section", "module.py#fn", "DOCUMENTS"),
        ]
    )
    result = assess_impact(graph, "module.py#fn", max_depth=4, max_candidates=300)
    assert result.candidates == []


def test_assess_impact_basis_path_from_start_to_candidate():
    graph = _graph(
        [
            ("caller.py#outer", "mid.py#helper", "CALL"),
            ("mid.py#helper", "target.py#fn", "CALL"),
        ]
    )
    result = assess_impact(graph, "target.py#fn", max_depth=4, max_candidates=300)
    by_cid = {c.canonical_id: c for c in result.candidates}
    assert by_cid["caller.py#outer"].basis[0].path == [
        "target.py#fn",
        "mid.py#helper",
        "caller.py#outer",
    ]
    assert by_cid["caller.py#outer"].basis[0].hop_distance == 2


def test_assess_impact_is_a_candidate_set_never_a_guarantee_claim():
    """No field on ImpactResult/ImpactCandidate asserts certainty --
    this test exists to pin that contract as the set of fields grows."""
    graph = _graph([("caller.py#outer", "target.py#fn", "CALL")])
    result = assess_impact(graph, "target.py#fn", max_depth=4, max_candidates=300)
    candidate_fields = set(result.candidates[0].__dataclass_fields__)
    assert candidate_fields == {"canonical_id", "file_path", "basis"}


def test_assess_impact_truncates_within_budget():
    edges = [(f"caller{i}.py#fn", "target.py#fn", "CALL") for i in range(10)]
    graph = _graph(edges)
    result = assess_impact(graph, "target.py#fn", max_depth=4, max_candidates=3)
    assert result.truncated
    assert len(result.candidates) <= 3
