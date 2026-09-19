# rag_orchestrator/tests/test_evidence_sufficiency.py
"""
Issue #200, Stage A1: pure function tests for the mechanical
evidence-sufficiency assessor -- no DB/HTTP, hand-built ORIENT-response
dicts and small CodebaseGraph fixtures via TRACE/IMPACT.

See specs/007-bounded-evidence-sufficiency/spec.md for the scenario-level
contract these tests verify.
"""

import pytest

from src.retrieval.codebase_queries import CodebaseGraph, Node
from src.retrieval.evidence_sufficiency import (
    assess_impact,
    assess_orient,
    assess_trace,
)
from src.retrieval.trace_impact import (
    AmbiguousStart,
    assess_impact as compute_impact,
    resolve_start_symbol,
    traced_path,
)

pytestmark = pytest.mark.unit


def _graph(
    edges: list[tuple[str, str, str]], extra_nodes: list[str] | None = None
) -> CodebaseGraph:
    graph = CodebaseGraph()
    all_cids = {cid for edge in edges for cid in (edge[0], edge[1])}
    all_cids |= set(extra_nodes or [])
    for cid in all_cids:
        file_path = cid.split("#", 1)[0]
        graph.add_node(Node(canonical_id=cid, file_path=file_path))
    for from_cid, to_cid, relation_type in edges:
        graph.add_edge(from_cid, to_cid, relation_type)
    return graph


# --- assess_orient ---


def test_orient_facet_with_records_is_satisfied():
    response = {"services": [{"name": "gradio"}], "gaps": []}
    result = assess_orient(response, required_facets=["services"])
    assert result.status == "satisfied"
    assert result.obligations == {"services": "satisfied"}
    assert result.evidence[0].identity == "services"
    assert result.missing_obligations == []


def test_orient_facet_with_explicit_gap_is_missing():
    response = {
        "docs_dirs": [],
        "gaps": [{"category": "docs_dirs", "reason": "no docs directory found"}],
    }
    result = assess_orient(response, required_facets=["docs_dirs"])
    assert result.status == "partial"
    assert result.obligations == {"docs_dirs": "missing"}
    assert "docs_dirs:inventory_gap" in result.reason_codes


def test_orient_facet_with_no_records_and_no_gap_is_unknown():
    response = {"test_dirs": [], "gaps": []}
    result = assess_orient(response, required_facets=["test_dirs"])
    assert result.status == "partial"
    assert result.obligations == {"test_dirs": "unknown"}
    assert "test_dirs:unsupported_facet" in result.reason_codes


def test_orient_unrelated_gap_does_not_satisfy_or_taint_other_facets():
    response = {
        "manifests": [{"kind": "pyproject", "path": "pyproject.toml"}],
        "gaps": [{"category": "docs_dirs", "reason": "no docs directory found"}],
    }
    result = assess_orient(response, required_facets=["manifests"])
    assert result.obligations == {"manifests": "satisfied"}


def test_orient_duplicate_required_facets_collapse_to_one_obligation():
    response = {"services": [{"name": "gradio"}], "gaps": []}
    result = assess_orient(response, required_facets=["services", "services"])
    assert result.obligations == {"services": "satisfied"}


def test_orient_multiple_required_facets_mixed_outcome():
    response = {
        "services": [{"name": "gradio"}],
        "docs_dirs": [],
        "gaps": [{"category": "docs_dirs", "reason": "no docs directory found"}],
    }
    result = assess_orient(response, required_facets=["services", "docs_dirs"])
    assert result.status == "partial"
    assert result.obligations == {"services": "satisfied", "docs_dirs": "missing"}
    assert result.missing_obligations == ["docs_dirs"]


# --- assess_trace ---


def test_trace_target_found_is_satisfied():
    graph = _graph([("a.py#foo", "b.py#bar", "CALL")])
    resolved = resolve_start_symbol(graph, "a.py#foo")
    trace = traced_path(
        graph, "a.py#foo", {"CALL"}, direction="forward", max_depth=6, max_nodes=300
    )
    result = assess_trace(resolved, trace, required_target="b.py#bar")
    assert result.status == "satisfied"
    assert result.obligations == {"start": "satisfied", "target": "satisfied"}


def test_trace_target_absent_fully_explored_frontier_is_missing():
    graph = _graph([("a.py#foo", "b.py#bar", "CALL")])
    resolved = resolve_start_symbol(graph, "a.py#foo")
    trace = traced_path(
        graph, "a.py#foo", {"CALL"}, direction="forward", max_depth=6, max_nodes=300
    )
    result = assess_trace(resolved, trace, required_target="z.py#nope")
    assert result.status == "partial"
    assert result.obligations["target"] == "missing"
    assert "target:not_in_explored_frontier" in result.reason_codes


def test_trace_target_absent_under_node_truncation_is_unknown():
    edges = [("a.py#foo", f"n{i}.py#x", "CALL") for i in range(10)]
    graph = _graph(edges)
    resolved = resolve_start_symbol(graph, "a.py#foo")
    trace = traced_path(
        graph, "a.py#foo", {"CALL"}, direction="forward", max_depth=6, max_nodes=3
    )
    result = assess_trace(resolved, trace, required_target="n9.py#x")
    assert result.status == "partial"
    assert result.obligations["target"] == "unknown"
    assert "target:node_truncated" in result.reason_codes


def test_trace_target_absent_under_depth_limit_is_unknown():
    graph = _graph(
        [("a.py#foo", "b.py#bar", "CALL"), ("b.py#bar", "c.py#baz", "CALL")]
    )
    resolved = resolve_start_symbol(graph, "a.py#foo")
    trace = traced_path(
        graph, "a.py#foo", {"CALL"}, direction="forward", max_depth=1, max_nodes=300
    )
    result = assess_trace(resolved, trace, required_target="c.py#baz")
    assert result.status == "partial"
    assert result.obligations["target"] == "unknown"
    assert "target:depth_limited" in result.reason_codes


def test_trace_no_required_target_is_satisfied_once_resolved():
    graph = _graph([("a.py#foo", "b.py#bar", "CALL")])
    resolved = resolve_start_symbol(graph, "a.py#foo")
    trace = traced_path(
        graph, "a.py#foo", {"CALL"}, direction="forward", max_depth=6, max_nodes=300
    )
    result = assess_trace(resolved, trace)
    assert result.status == "satisfied"
    assert result.obligations == {"start": "satisfied"}


def test_trace_ambiguous_start_needs_clarification():
    graph = _graph(
        [("a.py#foo", "a.py#dup", "CALL"), ("b.py#foo", "b.py#dup2", "CALL")]
    )
    resolved = resolve_start_symbol(graph, "foo")
    assert isinstance(resolved, AmbiguousStart)
    result = assess_trace(resolved, trace_result=None)
    assert result.status == "needs_clarification"
    assert result.obligations == {"start": "unknown"}
    assert result.missing_obligations == ["start"]


def test_trace_unresolved_start_is_missing():
    graph = _graph([("a.py#foo", "a.py#bar", "CALL")])
    resolved = resolve_start_symbol(graph, "does_not_exist")
    assert resolved is None
    result = assess_trace(resolved, trace_result=None)
    assert result.status == "partial"
    assert result.obligations == {"start": "missing"}


def test_trace_external_gap_is_reported_but_not_a_missing_obligation():
    graph = _graph([("a.py#foo", "EXTERNAL_SYMBOL:requests.get", "CALL")])
    resolved = resolve_start_symbol(graph, "a.py#foo")
    trace = traced_path(
        graph, "a.py#foo", {"CALL"}, direction="forward", max_depth=6, max_nodes=300
    )
    result = assess_trace(resolved, trace)
    assert result.status == "satisfied"
    assert any(code.startswith("external_gap:") for code in result.reason_codes)


# --- assess_impact ---


def test_impact_nonempty_untruncated_is_satisfied_no_truncation_code():
    graph = _graph([("caller.py#c1", "target.py#fn", "CALL")])
    resolved = resolve_start_symbol(graph, "target.py#fn")
    impact = compute_impact(graph, "target.py#fn", max_depth=4, max_candidates=300)
    result = assess_impact(resolved, impact)
    assert result.status == "satisfied"
    assert result.obligations == {"start": "satisfied", "candidate_set": "satisfied"}
    assert "scope:candidate_truncated" not in result.reason_codes
    assert len(result.evidence) == 1


def test_impact_empty_candidate_set_is_still_satisfied():
    graph = _graph([], extra_nodes=["target.py#fn"])
    resolved = resolve_start_symbol(graph, "target.py#fn")
    impact = compute_impact(graph, "target.py#fn", max_depth=4, max_candidates=300)
    result = assess_impact(resolved, impact)
    assert result.status == "satisfied"
    assert result.evidence == []


def test_impact_truncated_is_satisfied_with_truncation_reason_code():
    edges = [(f"c{i}.py#fn", "target.py#fn", "CALL") for i in range(10)]
    graph = _graph(edges)
    resolved = resolve_start_symbol(graph, "target.py#fn")
    impact = compute_impact(graph, "target.py#fn", max_depth=4, max_candidates=3)
    assert impact.truncated
    result = assess_impact(resolved, impact)
    assert result.status == "satisfied"
    assert "scope:candidate_truncated" in result.reason_codes


def test_impact_ambiguous_start_needs_clarification():
    graph = _graph(
        [("a.py#fn", "a.py#c1", "CALL"), ("b.py#fn", "b.py#c2", "CALL")]
    )
    resolved = resolve_start_symbol(graph, "fn")
    assert isinstance(resolved, AmbiguousStart)
    result = assess_impact(resolved, impact_result=None)
    assert result.status == "needs_clarification"


def test_impact_unresolved_start_is_missing():
    graph = _graph([("a.py#fn", "a.py#c1", "CALL")])
    resolved = resolve_start_symbol(graph, "does_not_exist")
    assert resolved is None
    result = assess_impact(resolved, impact_result=None)
    assert result.status == "partial"
    assert result.obligations == {"start": "missing"}
