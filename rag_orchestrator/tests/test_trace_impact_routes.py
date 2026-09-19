# rag_orchestrator/tests/test_trace_impact_routes.py
"""
Issue #198: route-level tests for GET /v1/repos/{repo_id}/trace and
/impact -- monkeypatch get_cached_graph (there's no outbound HTTP in
this path, unlike the ORIENT passthrough) to serve a hand-built fixture
graph, then hit the routes through a real TestClient.
"""

import pytest
from fastapi.testclient import TestClient

from src.api.v1.main import app
from src.retrieval.codebase_queries import CodebaseGraph, Node

pytestmark = pytest.mark.unit


def _fixture_graph() -> CodebaseGraph:
    graph = CodebaseGraph()
    for cid, path in [
        ("caller.py#outer", "caller.py"),
        ("mid.py#helper", "mid.py"),
        ("target.py#fn", "target.py"),
    ]:
        graph.add_node(Node(canonical_id=cid, file_path=path))
    graph.add_edge("caller.py#outer", "mid.py#helper", "CALL")
    graph.add_edge("mid.py#helper", "target.py#fn", "CALL")
    return graph


def _patch_graph(monkeypatch, graph: CodebaseGraph):
    def fake_get_cached_graph(repo_id, force_reload=False):
        return graph

    import src.retrieval.codebase_utils as codebase_utils

    monkeypatch.setattr(codebase_utils, "get_cached_graph", fake_get_cached_graph)


def test_trace_success(monkeypatch):
    _patch_graph(monkeypatch, _fixture_graph())
    client = TestClient(app)

    response = client.get(
        "/v1/repos/repo-x/trace",
        params={"start": "caller.py#outer", "relation_types": "CALL"},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["repo_id"] == "repo-x"
    assert body["resolved_start"]["canonical_id"] == "caller.py#outer"
    assert [h["canonical_id"] for h in body["hops"]] == [
        "mid.py#helper",
        "target.py#fn",
    ]
    assert body["truncated"] is False
    assert body["gaps"] == []


def test_trace_404_unresolvable_start(monkeypatch):
    _patch_graph(monkeypatch, _fixture_graph())
    client = TestClient(app)

    response = client.get("/v1/repos/repo-x/trace", params={"start": "nonexistent"})
    assert response.status_code == 404


def test_trace_409_ambiguous_start(monkeypatch):
    graph = CodebaseGraph()
    for cid, path in [
        ("service_a.py#run", "service_a.py"),
        ("service_b.py#run", "service_b.py"),
    ]:
        graph.add_node(Node(canonical_id=cid, file_path=path))
    _patch_graph(monkeypatch, graph)
    client = TestClient(app)

    response = client.get("/v1/repos/repo-x/trace", params={"start": "run"})
    assert response.status_code == 409
    assert "service_a.py#run" in response.json()["detail"]
    assert "service_b.py#run" in response.json()["detail"]


def test_trace_400_max_depth_over_cap(monkeypatch):
    _patch_graph(monkeypatch, _fixture_graph())
    client = TestClient(app)

    response = client.get(
        "/v1/repos/repo-x/trace",
        params={"start": "caller.py#outer", "max_depth": 999},
    )
    assert response.status_code == 400


def test_trace_400_bad_direction(monkeypatch):
    _patch_graph(monkeypatch, _fixture_graph())
    client = TestClient(app)

    response = client.get(
        "/v1/repos/repo-x/trace",
        params={"start": "caller.py#outer", "direction": "sideways"},
    )
    assert response.status_code == 400


def test_impact_success(monkeypatch):
    _patch_graph(monkeypatch, _fixture_graph())
    client = TestClient(app)

    response = client.get("/v1/repos/repo-x/impact", params={"start": "target.py#fn"})

    assert response.status_code == 200
    body = response.json()
    assert body["repo_id"] == "repo-x"
    candidate_ids = {c["canonical_id"] for c in body["candidates"]}
    assert candidate_ids == {"mid.py#helper", "caller.py#outer"}
    assert body["truncated"] is False


def test_impact_404_unresolvable_start(monkeypatch):
    _patch_graph(monkeypatch, _fixture_graph())
    client = TestClient(app)

    response = client.get("/v1/repos/repo-x/impact", params={"start": "nonexistent"})
    assert response.status_code == 404


def test_impact_400_max_depth_over_cap(monkeypatch):
    _patch_graph(monkeypatch, _fixture_graph())
    client = TestClient(app)

    response = client.get(
        "/v1/repos/repo-x/impact",
        params={"start": "target.py#fn", "max_depth": 999},
    )
    assert response.status_code == 400
