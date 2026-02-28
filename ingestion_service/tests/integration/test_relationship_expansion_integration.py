# ingestion_service/tests/integration/test_relationship_expansion_integration.py
import pytest
import uuid

from src.core.crud.document_nodes import create_document_node
from src.core.crud.document_relationships import create_document_relationship
from src.core.planner import expand_retrieval_plan

@pytest.mark.integration
def test_relationship_expansion_affects_candidate_set(session):
    """
    Verify that the planner expands seed documents via outgoing relationships (depth=1)
    using real Postgres DB (Docker-only).
    """
    # Create seed nodes
    doc1_id = str(uuid.uuid4())
    doc2_id = str(uuid.uuid4())
    seed_docs = [doc1_id]

    create_document_node(session, document_id=doc1_id, title="Seed Doc 1",repo_id = build_repo_id(repo_url), )
    create_document_node(session, document_id=doc2_id, title="Target Doc 2",repo_id = build_repo_id(repo_url), )

    # Add relationship: doc1 -> doc2
    create_document_relationship(
        session,
        from_document_id=doc1_id,
        to_document_id=doc2_id,
        relation_type="references"
    )

    # Run planner
    plan = expand_retrieval_plan(session, seed_docs)

    # Assertions
    assert doc1_id in plan.seed_document_ids
    assert doc2_id in plan.expanded_document_ids
    assert len(plan.expanded_document_ids) == 1  # depth=1
