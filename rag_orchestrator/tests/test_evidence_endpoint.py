# rag_orchestrator/tests/test_evidence_endpoint.py
"""
Issue #200, Stage A3: HTTP-level tests for POST /v1/repos/{repo_id}/evidence
-- mocked httpx (matching test_orient_passthrough.py's pattern) plus a
monkeypatched graph cache, no real network or DB.
"""

import httpx
import pytest
from fastapi.testclient import TestClient

from src.api.v1.main import app
from src.core import evidence_service
from src.retrieval.codebase_queries import CodebaseGraph, Node

pytestmark = pytest.mark.unit


def _patched_client(monkeypatch, handler):
    real_async_client = httpx.AsyncClient

    def patched(*args, **kwargs):
        kwargs["transport"] = httpx.MockTransport(handler)
        return real_async_client(*args, **kwargs)

    monkeypatch.setattr(httpx, "AsyncClient", patched)


def _generation_handler(generation_id: str = "gen-1", status: str = "ready"):
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith("/generation"):
            return httpx.Response(
                200, json={"ingestion_id": generation_id, "generation_status": status}
            )
        return httpx.Response(404)

    return handler


def _graph_with_edge() -> CodebaseGraph:
    graph = CodebaseGraph()
    graph.add_node(Node("a.py#foo", "a.py"))
    graph.add_node(Node("b.py#bar", "b.py"))
    graph.add_edge("a.py#foo", "b.py#bar", "CALL")
    return graph


# --- ORIENT ---


def test_orient_mode_satisfied(monkeypatch):
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith("/generation"):
            return httpx.Response(
                200, json={"ingestion_id": "gen-1", "generation_status": "ready"}
            )
        if request.url.path.endswith("/orient"):
            return httpx.Response(
                200,
                json={
                    "ingestion_id": "gen-1",
                    "services": [{"name": "gradio"}],
                    "gaps": [],
                },
            )
        return httpx.Response(404)

    _patched_client(monkeypatch, handler)
    client = TestClient(app)
    resp = client.post(
        "/v1/repos/repo-x/evidence",
        json={"mode": "orient", "required_facets": ["services"]},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["mode"] == "orient"
    assert body["assessment"]["status"] == "satisfied"
    assert body["stop_reason"] == "satisfied"


def test_orient_mode_rejects_start(monkeypatch):
    client = TestClient(app)
    resp = client.post(
        "/v1/repos/repo-x/evidence", json={"mode": "orient", "start": "a.py#foo"}
    )
    assert resp.status_code == 400


# --- TRACE ---


def test_trace_mode_target_found(monkeypatch):
    _patched_client(monkeypatch, _generation_handler())
    monkeypatch.setattr(
        evidence_service,
        "get_cached_graph_with_generation",
        lambda repo_id: ("gen-1", _graph_with_edge()),
    )
    client = TestClient(app)
    resp = client.post(
        "/v1/repos/repo-x/evidence",
        json={
            "mode": "trace",
            "start": "a.py#foo",
            "required_target": "b.py#bar",
        },
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["assessment"]["status"] == "satisfied"
    assert body["assessment"]["obligations"]["target"] == "satisfied"


def test_trace_mode_repairs_depth_limited_target(monkeypatch):
    graph = CodebaseGraph()
    graph.add_node(Node("a.py#foo", "a.py"))
    graph.add_node(Node("b.py#bar", "b.py"))
    graph.add_node(Node("c.py#baz", "c.py"))
    graph.add_edge("a.py#foo", "b.py#bar", "CALL")
    graph.add_edge("b.py#bar", "c.py#baz", "CALL")

    _patched_client(monkeypatch, _generation_handler())
    monkeypatch.setattr(
        evidence_service,
        "get_cached_graph_with_generation",
        lambda repo_id: ("gen-1", graph),
    )
    client = TestClient(app)
    resp = client.post(
        "/v1/repos/repo-x/evidence",
        json={
            "mode": "trace",
            "start": "a.py#foo",
            "required_target": "c.py#baz",
            "max_depth": 1,
        },
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["stop_reason"] == "repair_applied"
    assert [s["action"] for s in body["steps"]] == [
        "traced_path",
        "extend_frontier_to_server_ceiling",
    ]


def test_trace_mode_requires_start():
    client = TestClient(app)
    resp = client.post("/v1/repos/repo-x/evidence", json={"mode": "trace"})
    assert resp.status_code == 400


def test_trace_mode_max_depth_over_ceiling_is_400():
    client = TestClient(app)
    resp = client.post(
        "/v1/repos/repo-x/evidence",
        json={"mode": "trace", "start": "a.py#foo", "max_depth": 999},
    )
    assert resp.status_code == 400


# --- IMPACT ---


def test_impact_mode_satisfied_with_candidates(monkeypatch):
    graph = _graph_reverse_for_impact()
    _patched_client(monkeypatch, _generation_handler())
    monkeypatch.setattr(
        evidence_service,
        "get_cached_graph_with_generation",
        lambda repo_id: ("gen-1", graph),
    )
    client = TestClient(app)
    resp = client.post(
        "/v1/repos/repo-x/evidence",
        json={"mode": "impact", "start": "target.py#fn"},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["assessment"]["status"] == "satisfied"
    assert len(body["assessment"]["evidence"]) == 1


def _graph_reverse_for_impact() -> CodebaseGraph:
    graph = CodebaseGraph()
    graph.add_node(Node("caller.py#c1", "caller.py"))
    graph.add_node(Node("target.py#fn", "target.py"))
    graph.add_edge("caller.py#c1", "target.py#fn", "CALL")
    return graph


def test_impact_mode_requires_start():
    client = TestClient(app)
    resp = client.post("/v1/repos/repo-x/evidence", json={"mode": "impact"})
    assert resp.status_code == 400


def test_impact_mode_rejects_required_target():
    client = TestClient(app)
    resp = client.post(
        "/v1/repos/repo-x/evidence",
        json={"mode": "impact", "start": "a.py#foo", "required_target": "b.py#bar"},
    )
    assert resp.status_code == 400


# --- Stage A4: explanation_query ---


def test_trace_mode_with_explanation_query_returns_explanation(monkeypatch):
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith("/generation"):
            return httpx.Response(
                200, json={"ingestion_id": "gen-1", "generation_status": "ready"}
            )
        if request.url.path.endswith("/generate"):
            return httpx.Response(
                200,
                json={
                    "response": "yes, via CALL.",
                    "model": "llama3",
                    "model_alias": "default",
                    "fallback_from": None,
                },
            )
        return httpx.Response(404)

    _patched_client(monkeypatch, handler)
    monkeypatch.setattr(
        evidence_service,
        "get_cached_graph_with_generation",
        lambda repo_id: ("gen-1", _graph_with_edge()),
    )
    client = TestClient(app)
    resp = client.post(
        "/v1/repos/repo-x/evidence",
        json={
            "mode": "trace",
            "start": "a.py#foo",
            "required_target": "b.py#bar",
            "explanation_query": "is b.py#bar reachable?",
        },
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["explanation"]["answer"] == "yes, via CALL."
    assert body["explanation"]["model_used"] == "llama3"


def test_mode_without_explanation_query_has_null_explanation(monkeypatch):
    _patched_client(monkeypatch, _generation_handler())
    monkeypatch.setattr(
        evidence_service,
        "get_cached_graph_with_generation",
        lambda repo_id: ("gen-1", _graph_with_edge()),
    )
    client = TestClient(app)
    resp = client.post(
        "/v1/repos/repo-x/evidence",
        json={"mode": "trace", "start": "a.py#foo"},
    )
    assert resp.status_code == 200
    assert resp.json()["explanation"] is None


# --- generation lifecycle failures propagate as HTTP errors ---


def test_generation_not_ready_is_503(monkeypatch):
    _patched_client(monkeypatch, _generation_handler(status="building"))
    client = TestClient(app)
    resp = client.post(
        "/v1/repos/repo-x/evidence",
        json={"mode": "orient", "required_facets": ["services"]},
    )
    assert resp.status_code == 503
