# ingestion_service/tests/test_retrieval_planner.py
import pytest
from src.core.retrieval.retrieval_plan import RetrievalPlan  
from src.core.planner import expand_retrieval_plan

from src.core.crud.document_relationships import DocumentRelationship

# Mock relationships
class MockSession:
    def __init__(self, relationships):
        self.relationships = relationships

    def query(self, model):
        return self

    def filter_by(self, **kwargs):
        # Only supports from_document_id filtering
        from_id = kwargs.get("from_document_id")
        filtered = [r for r in self.relationships if r.from_document_id == from_id]
        self._results = filtered
        return self

    def all(self):
        return getattr(self, "_results", [])

# Simple DocumentRelationship stub
class MockRelationship:
    def __init__(self, from_document_id, to_document_id):
        self.from_document_id = from_document_id
        self.to_document_id = to_document_id
        self.relation_type = "any"

@pytest.mark.unit
def test_no_relationships():
    seeds = ["doc1", "doc2"]
    session = MockSession([])
    plan = expand_retrieval_plan(session, seeds)
    assert set(plan.seed_document_ids) == set(seeds)
    assert plan.expanded_document_ids == []

@pytest.mark.unit
def test_single_outgoing_relationship():
    seeds = ["doc1"]
    rels = [MockRelationship("doc1", "doc2")]
    session = MockSession(rels)
    plan = expand_retrieval_plan(session, seeds)
    assert "doc2" in plan.expanded_document_ids

@pytest.mark.unit
def test_multiple_seeds_overlap():
    seeds = ["doc1", "doc2"]
    rels = [
        MockRelationship("doc1", "doc3"),
        MockRelationship("doc2", "doc3"),
        MockRelationship("doc2", "doc4"),
    ]
    session = MockSession(rels)
    plan = expand_retrieval_plan(session, seeds)
    # expanded_document_ids should include all unique targets
    assert set(plan.expanded_document_ids) == {"doc3", "doc4"}
