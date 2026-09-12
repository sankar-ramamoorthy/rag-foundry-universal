# ingestion_service/tests/test_graph_canonical_lookup.py
"""
Issue #107: GET /v1/graph/repos/{repo_id}/nodes takes canonical_ids as a
comma-separated query string, which can overflow the server's URL/header
length limit once enough IDs are batched together (confirmed live: a
344-canonical_id GET request returned HTTP 400 "Invalid HTTP request
received", silently swallowed by rag_orchestrator's caller into an empty
mapping indistinguishable from "nothing matched"). POST
/v1/graph/repos/{repo_id}/nodes/lookup carries the same IDs in a JSON
body instead, with no such practical size limit -- this is the endpoint
rag_orchestrator.canonical_to_document_map_http now uses.

These are pure unit tests of the route functions directly (no DB, no
FastAPI TestClient/app-startup, no Docker) -- db_utils is monkeypatched.
"""
import asyncio
from dataclasses import dataclass
from typing import List

import pytest

from src.api.v1 import graph as graph_module
from src.api.v1.graph import (
    CanonicalLookupRequest,
    get_nodes_by_canonical_ids,
    post_nodes_by_canonical_ids,
)

pytestmark = pytest.mark.unit


@dataclass
class FakeDocumentNode:
    document_id: str
    canonical_id: str
    relative_path: str
    title: str
    doc_type: str


def _fake_lookup(expected_repo_id, nodes_by_cid):
    def _lookup(repo_id: str, cids: List[str]):
        assert repo_id == expected_repo_id
        return [nodes_by_cid[cid] for cid in cids if cid in nodes_by_cid]

    return _lookup


def test_post_lookup_resolves_a_large_canonical_id_batch(monkeypatch):
    """The exact failure mode issue #107 found: hundreds of canonical_ids
    in one request must all resolve, not silently come back empty."""
    n = 400
    nodes_by_cid = {
        f"pkg/module_{i}.py#func_{i}": FakeDocumentNode(
            document_id=f"doc-{i}",
            canonical_id=f"pkg/module_{i}.py#func_{i}",
            relative_path=f"pkg/module_{i}.py",
            title=f"func_{i}",
            doc_type="python source",
        )
        for i in range(n)
    }
    monkeypatch.setattr(
        graph_module.db_utils,
        "get_document_nodes_by_canonical_ids",
        _fake_lookup("repo-x", nodes_by_cid),
    )

    response = asyncio.run(
        post_nodes_by_canonical_ids(
            "repo-x", CanonicalLookupRequest(canonical_ids=list(nodes_by_cid.keys()))
        )
    )

    assert response.total == n
    assert {node.canonical_id for node in response.nodes} == set(nodes_by_cid.keys())


def test_post_lookup_empty_ids_returns_empty_without_calling_db(monkeypatch):
    called = []
    monkeypatch.setattr(
        graph_module.db_utils,
        "get_document_nodes_by_canonical_ids",
        lambda repo_id, cids: called.append(cids) or [],
    )

    response = asyncio.run(
        post_nodes_by_canonical_ids(
            "repo-x", CanonicalLookupRequest(canonical_ids=["", "  "])
        )
    )

    assert response == graph_module.CanonicalLookupResponse(nodes=[], total=0)
    assert called == []


def test_get_and_post_agree_for_the_same_small_batch(monkeypatch):
    """The GET form stays for small/ad hoc lookups -- both forms must
    resolve identically for a batch small enough that GET still works."""
    nodes_by_cid = {
        "a.py": FakeDocumentNode("doc-a", "a.py", "a.py", "a", "python source"),
        "b.py#f": FakeDocumentNode("doc-b", "b.py#f", "b.py", "f", "python source"),
    }
    monkeypatch.setattr(
        graph_module.db_utils,
        "get_document_nodes_by_canonical_ids",
        _fake_lookup("repo-x", nodes_by_cid),
    )

    get_response = asyncio.run(get_nodes_by_canonical_ids("repo-x", "a.py,b.py#f"))
    post_response = asyncio.run(
        post_nodes_by_canonical_ids(
            "repo-x", CanonicalLookupRequest(canonical_ids=["a.py", "b.py#f"])
        )
    )

    assert get_response == post_response
