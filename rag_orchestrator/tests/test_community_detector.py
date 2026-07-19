# rag_orchestrator/tests/test_community_detector.py
# Issue #24: recovered from the tests/__init__.py directory that broke
# collection; import path updated.

import pytest

from src.retrieval.community_detector import cluster_documents

pytestmark = pytest.mark.unit


@pytest.mark.parametrize(
    "document_ids,metadata,expected",
    [
        # No metadata → single cluster, sorted
        (["D3", "D1", "D2"], None, [["D1", "D2", "D3"]]),

        # Metadata present → cluster by project_phase
        (
            ["D1", "D2", "D3", "D4"],
            {
                "D1": {"project_phase": "planning"},
                "D2": {"project_phase": "execution"},
                "D3": {"project_phase": "planning"},
                "D4": {"project_phase": "execution"},
            },
            [["D2", "D4"], ["D1", "D3"]],  # sorted clusters by key, docs sorted
        ),

        # Missing cluster key → UNKNOWN ("UNKNOWN" sorts before lowercase keys)
        (
            ["D1", "D2", "D3"],
            {
                "D1": {"project_phase": "planning"},
                "D3": {"some_other_key": "x"},
            },
            [["D2", "D3"], ["D1"]],
        ),

        # Empty document list
        ([], None, []),
    ],
)
def test_cluster_documents(document_ids, metadata, expected):
    clusters = cluster_documents(document_ids=document_ids, metadata=metadata)
    assert clusters == expected
