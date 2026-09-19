# rag_orchestrator/tests/test_evidence_workflow.py
"""
Issue #200, Stage A2: pure function tests for the bounded evidence
control loop -- no DB/HTTP, hand-built CodebaseGraph fixtures and ORIENT
response dicts, same style as test_evidence_sufficiency.py.
"""

import pytest

from src.retrieval.codebase_queries import CodebaseGraph, Node
from src.retrieval.evidence_workflow import (
    MAX_REPAIR_ACTIONS,
    run_impact_workflow,
    run_orient_workflow,
    run_trace_workflow,
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


# --- ORIENT: no repair capability ---


def test_orient_satisfied_single_pass_no_repair():
    response = {"services": [{"name": "gradio"}], "gaps": []}
    result = run_orient_workflow(response, required_facets=["services"])
    assert result.assessment.status == "satisfied"
    assert result.stop_reason == "satisfied"
    assert len(result.steps) == 1


def test_orient_gap_reports_no_repair_capability_not_a_retry():
    response = {"docs_dirs": [], "gaps": []}
    result = run_orient_workflow(response, required_facets=["docs_dirs"])
    assert result.assessment.status == "partial"
    assert result.stop_reason == "no_repair_capability"
    assert len(result.steps) == 1  # no second pass was attempted


# --- TRACE: the one obligation-driven repair Stage A supports ---


def test_trace_satisfied_at_requested_depth_no_repair_attempted():
    graph = _graph([("a.py#foo", "b.py#bar", "CALL")])
    result = run_trace_workflow(
        graph,
        "a.py#foo",
        {"CALL"},
        direction="forward",
        requested_max_depth=6,
        server_max_depth=6,
        max_nodes=300,
        required_target="b.py#bar",
    )
    assert result.assessment.status == "satisfied"
    assert result.stop_reason == "satisfied"
    assert len(result.steps) == 1


def test_trace_depth_limited_target_is_repaired_to_server_ceiling():
    graph = _graph(
        [("a.py#foo", "b.py#bar", "CALL"), ("b.py#bar", "c.py#baz", "CALL")]
    )
    result = run_trace_workflow(
        graph,
        "a.py#foo",
        {"CALL"},
        direction="forward",
        requested_max_depth=1,
        server_max_depth=6,
        max_nodes=300,
        required_target="c.py#baz",
    )
    assert result.assessment.status == "satisfied"
    assert result.stop_reason == "repair_applied"
    assert [s.action for s in result.steps] == [
        "traced_path",
        "extend_frontier_to_server_ceiling",
    ]
    assert result.steps[-1].outcome == "progress"
    # Exactly one repair action -- never more, per MAX_REPAIR_ACTIONS.
    assert len([s for s in result.steps if s.action != "traced_path"]) <= (
        MAX_REPAIR_ACTIONS
    )


def test_trace_missing_target_fully_explored_frontier_no_repair():
    """A fully-explored frontier without the target cannot be helped by
    more depth -- extending would just be repeated work for no chance of
    progress, so no repair is attempted."""
    graph = _graph([("a.py#foo", "b.py#bar", "CALL")])
    result = run_trace_workflow(
        graph,
        "a.py#foo",
        {"CALL"},
        direction="forward",
        requested_max_depth=6,
        server_max_depth=6,
        max_nodes=300,
        required_target="z.py#nope",
    )
    assert result.assessment.status == "partial"
    assert result.assessment.obligations["target"] == "missing"
    assert result.stop_reason == "no_useful_repair"
    assert len(result.steps) == 1


def test_trace_already_at_server_ceiling_cannot_repair_further():
    edges = [("a.py#foo", f"n{i}.py#x", "CALL") for i in range(10)]
    graph = _graph(edges)
    result = run_trace_workflow(
        graph,
        "a.py#foo",
        {"CALL"},
        direction="forward",
        requested_max_depth=6,
        server_max_depth=6,
        max_nodes=3,
        required_target="n9.py#x",
    )
    assert result.assessment.obligations["target"] == "unknown"
    assert result.stop_reason == "no_useful_repair"


def test_trace_repair_reclassifies_unknown_to_missing_as_progress():
    """The repaired (now fully-explored) frontier still doesn't contain
    the target -- but going from `unknown` (bounded cutoff, might exist
    past the cap) to `missing` (fully explored, genuinely absent) is
    itself progress: the repair resolved a real uncertainty, even though
    the target obligation is still not satisfied. Either way, the loop
    stops after this one repair rather than trying again."""
    graph = _graph(
        [("a.py#foo", "b.py#bar", "CALL"), ("b.py#bar", "c.py#baz", "CALL")]
    )
    result = run_trace_workflow(
        graph,
        "a.py#foo",
        {"CALL"},
        direction="forward",
        requested_max_depth=1,
        server_max_depth=6,
        max_nodes=300,
        required_target="does.py#not_exist",
    )
    assert result.stop_reason == "repair_applied"
    assert result.steps[-1].outcome == "progress"
    assert result.assessment.obligations["target"] == "missing"
    assert result.assessment.status == "partial"


def test_trace_repair_still_node_truncated_is_no_progress():
    """Extending depth cannot help when the real bottleneck is the node
    cap, not the depth cap -- the repair is still attempted (obligation
    was `unknown`) but the outcome is `no_progress` once it doesn't
    change the classification."""
    edges = [("a.py#foo", f"n{i}.py#x", "CALL") for i in range(10)]
    graph = _graph(edges)
    result = run_trace_workflow(
        graph,
        "a.py#foo",
        {"CALL"},
        direction="forward",
        requested_max_depth=1,
        server_max_depth=6,
        max_nodes=3,
        required_target="n9.py#x",
    )
    assert result.stop_reason == "repair_applied"
    assert result.steps[-1].outcome == "no_progress"
    assert result.assessment.obligations["target"] == "unknown"


def test_trace_ambiguous_start_no_repair_attempted():
    graph = _graph(
        [("a.py#foo", "a.py#dup", "CALL"), ("b.py#foo", "b.py#dup2", "CALL")]
    )
    result = run_trace_workflow(
        graph, "foo", {"CALL"}, direction="forward",
        requested_max_depth=1, server_max_depth=6, max_nodes=300,
    )
    assert result.stop_reason == "needs_clarification"
    assert result.steps == []


def test_trace_unresolved_start_no_repair_attempted():
    graph = _graph([("a.py#foo", "a.py#bar", "CALL")])
    result = run_trace_workflow(
        graph, "does_not_exist", {"CALL"}, direction="forward",
        requested_max_depth=1, server_max_depth=6, max_nodes=300,
    )
    assert result.stop_reason == "unresolved_start"
    assert result.steps == []


def test_trace_without_required_target_never_repairs():
    """No target obligation means nothing to repair, even if the trace
    was depth-limited -- Stage A never repairs a scope nobody asked to
    fully cover."""
    graph = _graph(
        [("a.py#foo", "b.py#bar", "CALL"), ("b.py#bar", "c.py#baz", "CALL")]
    )
    result = run_trace_workflow(
        graph, "a.py#foo", {"CALL"}, direction="forward",
        requested_max_depth=1, server_max_depth=6, max_nodes=300,
    )
    assert result.assessment.status == "satisfied"
    assert result.stop_reason == "satisfied"
    assert len(result.steps) == 1


# --- IMPACT: candidate-set obligation is always satisfied, never repaired ---


def test_impact_never_repairs_even_when_truncated():
    edges = [(f"c{i}.py#fn", "target.py#fn", "CALL") for i in range(10)]
    graph = _graph(edges)
    result = run_impact_workflow(
        graph, "target.py#fn", max_depth=4, max_candidates=3
    )
    assert result.assessment.status == "satisfied"
    assert result.stop_reason == "satisfied"
    assert len(result.steps) == 1
    assert "scope:candidate_truncated" in result.assessment.reason_codes


def test_impact_ambiguous_start_no_repair():
    graph = _graph([("a.py#fn", "a.py#c1", "CALL"), ("b.py#fn", "b.py#c2", "CALL")])
    result = run_impact_workflow(graph, "fn", max_depth=4, max_candidates=300)
    assert result.stop_reason == "needs_clarification"
