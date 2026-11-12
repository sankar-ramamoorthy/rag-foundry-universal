"""Issue #345/#342 retrieval-candidate capture: pure helpers only.

The capture itself needs the deployed services; these tests cover the
ranking arithmetic and witness bookkeeping it reports.
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import retrieval_candidates_345 as rc  # noqa: E402


def test_similarity_position_within_and_beyond_deep_k():
    deep = [0.9, 0.8, 0.7, 0.6]
    assert rc.similarity_position(0.75, deep) == {"rank": 3, "beyond_deep_k": False}
    assert rc.similarity_position(0.95, deep) == {"rank": 1, "beyond_deep_k": False}
    assert rc.similarity_position(0.5, deep) == {"rank": None, "beyond_deep_k": True}
    assert rc.similarity_position(None, deep) == {"rank": None, "beyond_deep_k": None}


def test_witnesses_follow_reviewed_excerpts_plus_factory():
    assert rc.WITNESSES[0] == "rag_orchestrator/src/api/v1/routes.py#rag_endpoint"
    i = rc.WITNESSES.index("shared/embedders/factory.py#get_embedder")
    assert rc.WITNESSES[i + 1] == "shared/embedders/query.py#embed_query"
    assert len(rc.WITNESSES) == len(set(rc.WITNESSES)) == 10


def test_nodes_of_keeps_only_witnesses():
    lookup = {
        "nodes": [
            {"canonical_id": rc.WITNESSES[0], "document_id": "d1"},
            {"canonical_id": "other.py#x", "document_id": "d2"},
        ]
    }
    assert list(rc.nodes_of(lookup)) == [rc.WITNESSES[0]]


def test_chunk_row_reads_nested_metadata():
    chunk = {
        "chunk_id": "c",
        "document_id": "d",
        "text": "abc",
        "score": 0.7,
        "metadata": {"source_metadata": {"doc_type": "python source",
                                         "source_type": "code",
                                         "canonical_id": "a.py#f"}},
    }
    row = rc.chunk_row(1, chunk, lambda c: "a.py#f")
    assert row["doc_type"] == "python source" and row["source_type"] == "code"
    assert row["bytes"] == 3 and row["label"] == "a.py#f"
