# rag_orchestrator/tests/test_traversal_planner.py

import pytest

from shared.retrieval_plan import RetrievalPlan
from rag_orchestrator.src.retrieval.traversal_planner import (
    expand_retrieval_plan,
    TraversalConstraints,
)


# -----------------------
# Mock helper
# -----------------------
def make_mock_relationships(rel_map):
    """
    Returns a list_outgoing_relationships function for testing.

    rel_map: Dict[document_id, List[Dict]]
    """
    def _list_outgoing(document_id):
        return rel_map.get(document_id, [])
    return _list_outgoing


# -----------------------
# Test cases
# -----------------------
def test_no_relationships():
    """
    If there are no outgoing relationships, plan should be unchanged.
    """
    plan = RetrievalPlan(
        seed_document_ids=["A"],
        expanded_document_ids=[],
        expansion_metadata=[],
        constraints=None,
    )

    list_outgoing = make_mock_relationships({})

    new_plan = expand_retrieval_plan(
        plan=plan,
        list_outgoing_relationships=list_outgoing,
        constraints=TraversalConstraints(max_depth=2),
    )

    assert new_plan.seed_document_ids == ["A"]
    assert new_plan.expanded_document_ids == []
    assert len(new_plan.expansion_metadata) == 0


def test_single_hop_expansion():
    """
    Single outgoing relationship should be included in expanded_document_ids.
    """
    plan = RetrievalPlan(
        seed_document_ids=["A"],
        expanded_document_ids=[],
        expansion_metadata=[],
        constraints=TraversalConstraints(max_depth=1),
    )

    rel_map = {
        "A": [{"target_document_id": "B", "relation_type": "relates_to"}]
    }
    list_outgoing = make_mock_relationships(rel_map)

    new_plan = expand_retrieval_plan(
        plan=plan,
        list_outgoing_relationships=list_outgoing,
        constraints=TraversalConstraints(max_depth=1),
    )

    assert "B" in new_plan.expanded_document_ids
    # Seed should remain
    assert new_plan.seed_document_ids == ["A"]


def test_multi_hop_respects_max_depth():
    """
    Should not traverse beyond max_depth
    """
    plan = RetrievalPlan(
        seed_document_ids=["A"],
        expanded_document_ids=[],
        expansion_metadata=[],
        constraints=None,
    )

    rel_map = {
        "A": [{"target_document_id": "B", "relation_type": "r1"}],
        "B": [{"target_document_id": "C", "relation_type": "r2"}],
        "C": [{"target_document_id": "D", "relation_type": "r3"}],
    }
    list_outgoing = make_mock_relationships(rel_map)

    # Max depth = 2 should include B and C, but not D
    new_plan = expand_retrieval_plan(
        plan=plan,
        list_outgoing_relationships=list_outgoing,
        constraints=TraversalConstraints(max_depth=2),
    )

    assert "B" in new_plan.expanded_document_ids
    assert "C" in new_plan.expanded_document_ids
    assert "D" not in new_plan.expanded_document_ids


def test_allowed_relation_types_filtering():
    """
    Only relationships of allowed types should be followed
    """
    plan = RetrievalPlan(
        seed_document_ids=["A"],
        expanded_document_ids=[],
        expansion_metadata=[],
        constraints=None,
    )

    rel_map = {
        "A": [
            {"target_document_id": "B", "relation_type": "allowed"},
            {"target_document_id": "C", "relation_type": "blocked"},
        ]
    }
    list_outgoing = make_mock_relationships(rel_map)

    new_plan = expand_retrieval_plan(
        plan=plan,
        list_outgoing_relationships=list_outgoing,
        constraints=TraversalConstraints(max_depth=1, allowed_relation_types={"allowed"}),
    )

    assert "B" in new_plan.expanded_document_ids
    assert "C" not in new_plan.expanded_document_ids


def test_deterministic_ordering():
    """
    Traversal should always return the same order of expansions
    """
    plan = RetrievalPlan(
        seed_document_ids=["A", "X"],
        expanded_document_ids=[],
        expansion_metadata=[],
        constraints=TraversalConstraints(max_depth=1),
    )

    rel_map = {
        "A": [{"target_document_id": "B", "relation_type": "r"}],
        "X": [{"target_document_id": "Y", "relation_type": "r"}],
    }
    list_outgoing = make_mock_relationships(rel_map)

    first_run = expand_retrieval_plan(plan=plan, list_outgoing_relationships=list_outgoing, constraints=TraversalConstraints(max_depth=1))
    second_run = expand_retrieval_plan(plan=plan, list_outgoing_relationships=list_outgoing, constraints=TraversalConstraints(max_depth=1))

    assert first_run.expanded_document_ids == second_run.expanded_document_ids
