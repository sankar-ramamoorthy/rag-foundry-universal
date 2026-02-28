# rag_orchestrator/src/retrieval/traversal_planner.py

from dataclasses import dataclass
from typing import List, Dict, Set, Optional, Callable

from shared.retrieval.retrieval_plan import RetrievalPlan, ExpansionMetadata, RetrievalConstraints


@dataclass(frozen=True)
class TraversalConstraints:
    """Limits for controlled graph traversal in retrieval planning."""
    max_depth: int = 1
    allowed_relation_types: Optional[Set[str]] = None  # None = all allowed


def expand_retrieval_plan(
    *,
    plan: RetrievalPlan,
    list_outgoing_relationships: Callable[[str], List[Dict]],  # document_id -> List[dict]
    constraints: TraversalConstraints,
) -> RetrievalPlan:
    """
    Extend a RetrievalPlan with additional documents via controlled traversal.

    Behavior:
    - Traverses outgoing relationships only
    - Stops at max_depth
    - Respects allowed_relation_types if provided
    - Deterministic order
    - Does NOT modify original plan; returns a new plan object

    Expansion metadata now tracks:
    - source_document_id: which document caused this expansion
    - relation_type: which relation type was followed
    """

    expanded_ids: Set[str] = set()
    visited: Set[str] = set(plan.seed_document_ids) | plan.expanded_document_ids
    new_expansion_metadata: Dict[str, ExpansionMetadata] = dict(plan.expansion_metadata)

    def _traverse(doc_id: str, depth: int):
        if depth > constraints.max_depth:
            return

        outgoing = list_outgoing_relationships(doc_id)
        outgoing_sorted = sorted(outgoing, key=lambda r: r['target_document_id'])

        for rel in outgoing_sorted:
            target_id = rel['target_document_id']
            relation_type = rel.get('relation_type')

            # Skip disallowed types
            if constraints.allowed_relation_types and relation_type not in constraints.allowed_relation_types:
                continue

            if target_id not in visited:
                visited.add(target_id)
                expanded_ids.add(target_id)

                # Record metadata: exact edge traversed
                new_expansion_metadata[target_id] = ExpansionMetadata(
                    source_document_id=doc_id,
                    relation_type=relation_type or "UNKNOWN"
                )

                _traverse(target_id, depth + 1)

    # Begin traversal from all seeds
    for seed_id in plan.seed_document_ids:
        _traverse(seed_id, depth=1)

    return RetrievalPlan(
        seed_document_ids=set(plan.seed_document_ids),
        expanded_document_ids=plan.expanded_document_ids | expanded_ids,
        expansion_metadata=new_expansion_metadata,
        constraints=plan.constraints,
    )
