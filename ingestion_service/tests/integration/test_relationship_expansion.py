import pytest
from sqlalchemy.orm import Session
import uuid

from src.core.crud.document_relationships import create_document_relationship
from src.core.crud.crud_document_node import create_document_node
from src.core.planners.relationship_expansion import expand_relationships_one_hop
from shared.retrieval.retrieval_plan import RetrievalPlan 
from src.core.codebase.identity import build_repo_id

@pytest.mark.integration
def test_expand_relationships_one_hop(session: Session):
    """
    MS4-IS2: Verify deterministic one-hop expansion of seed documents.

    Scenario:
    - Create 3 DocumentNodes: A, B, C
    - Create relationships: A -> B, A -> C, B -> C
    - Seed: [A]
    Expected:
    - expanded_document_ids: [B, C]
    - expansion_metadata includes both A->B and A->C
    """
    # Unique IDs for this test run
    doc_a_id = str(uuid.uuid4())
    doc_b_id = str(uuid.uuid4())
    doc_c_id = str(uuid.uuid4())

    # Create document nodes
    create_document_node(session, document_id=doc_a_id, content="Doc A",repo_id = build_repo_id(repo_url), )
    create_document_node(session, document_id=doc_b_id, content="Doc B"repo_id = build_repo_id(repo_url), )
    create_document_node(session, document_id=doc_c_id, content="Doc C"repo_id = build_repo_id(repo_url), )

    # Create relationships
    create_document_relationship(session, from_document_id=doc_a_id, to_document_id=doc_b_id, relation_type="refers")
    create_document_relationship(session, from_document_id=doc_a_id, to_document_id=doc_c_id, relation_type="refers")
    create_document_relationship(session, from_document_id=doc_b_id, to_document_id=doc_c_id, relation_type="cites")

    # Run planner
    plan: RetrievalPlan = expand_relationships_one_hop(session=session, seed_document_ids=[doc_a_id])

    # Assert seed documents unchanged
    assert plan.seed_document_ids == [doc_a_id]

    # Expanded documents should only include direct outgoing relationships from A
    assert set(plan.expanded_document_ids) == {doc_b_id, doc_c_id}

    # Expansion metadata includes A->B and A->C
    metadata_pairs = {(m["from_document_id"], m["to_document_id"]) for m in plan.expansion_metadata}
    assert metadata_pairs == {(doc_a_id, doc_b_id), (doc_a_id, doc_c_id)}

    # Constraints are correct
    assert plan.constraints == {"depth": 1, "traversal": "outgoing"}
