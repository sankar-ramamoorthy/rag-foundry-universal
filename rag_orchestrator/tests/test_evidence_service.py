# rag_orchestrator/tests/test_evidence_service.py
"""
Issue #200, Stage A2: generation-fence tests for the evidence workflow
adapters -- mocked httpx (matching test_evidence_survival.py's/test_
orient_passthrough.py's pattern) plus a monkeypatched graph cache, no
real network or DB.
"""

import asyncio

import httpx
import pytest
from fastapi import HTTPException

from src.core import evidence_service
from src.retrieval.codebase_queries import CodebaseGraph, Node

pytestmark = pytest.mark.unit


def _patched_httpx(monkeypatch, handler):
    real_async_client = httpx.AsyncClient

    def patched(*args, **kwargs):
        kwargs["transport"] = httpx.MockTransport(handler)
        return real_async_client(*args, **kwargs)

    monkeypatch.setattr(httpx, "AsyncClient", patched)


def _generation_handler(generation_id: str, status: str = "ready"):
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


def test_orient_evidence_happy_path(monkeypatch):
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

    _patched_httpx(monkeypatch, handler)
    result = asyncio.run(
        evidence_service.run_orient_evidence("repo-x", required_facets=["services"])
    )
    assert result.assessment.status == "satisfied"
    assert result.stop_reason == "satisfied"


def test_orient_evidence_generation_mismatch_is_409(monkeypatch):
    """ORIENT's own response claims a different generation than the one
    just resolved as ready -- a race with an in-flight rebuild -- and
    must fail loudly rather than silently mixing generations."""

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith("/generation"):
            return httpx.Response(
                200, json={"ingestion_id": "gen-2", "generation_status": "ready"}
            )
        if request.url.path.endswith("/orient"):
            return httpx.Response(
                200, json={"ingestion_id": "gen-1", "services": [], "gaps": []}
            )
        return httpx.Response(404)

    _patched_httpx(monkeypatch, handler)
    with pytest.raises(HTTPException) as exc_info:
        asyncio.run(
            evidence_service.run_orient_evidence("repo-x", required_facets=["services"])
        )
    assert exc_info.value.status_code == 409


def test_orient_evidence_not_ready_propagates_503(monkeypatch):
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith("/generation"):
            return httpx.Response(
                200, json={"ingestion_id": None, "generation_status": "building"}
            )
        return httpx.Response(404)

    _patched_httpx(monkeypatch, handler)
    with pytest.raises(HTTPException) as exc_info:
        asyncio.run(
            evidence_service.run_orient_evidence("repo-x", required_facets=["services"])
        )
    assert exc_info.value.status_code == 503


def test_orient_evidence_404_propagates(monkeypatch):
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith("/generation"):
            return httpx.Response(
                200, json={"ingestion_id": "gen-1", "generation_status": "ready"}
            )
        if request.url.path.endswith("/orient"):
            return httpx.Response(404, json={"detail": "No completed generation"})
        return httpx.Response(404)

    _patched_httpx(monkeypatch, handler)
    with pytest.raises(HTTPException) as exc_info:
        asyncio.run(
            evidence_service.run_orient_evidence("repo-x", required_facets=["services"])
        )
    assert exc_info.value.status_code == 404


# --- TRACE / IMPACT ---


def test_trace_evidence_happy_path(monkeypatch):
    _patched_httpx(monkeypatch, _generation_handler("gen-1"))
    monkeypatch.setattr(
        evidence_service,
        "get_cached_graph_with_generation",
        lambda repo_id: ("gen-1", _graph_with_edge()),
    )

    result = asyncio.run(
        evidence_service.run_trace_evidence(
            "repo-x",
            "a.py#foo",
            {"CALL"},
            direction="forward",
            requested_max_depth=6,
            server_max_depth=6,
            max_nodes=300,
            required_target="b.py#bar",
        )
    )
    assert result.assessment.status == "satisfied"


def test_trace_evidence_graph_generation_mismatch_is_409(monkeypatch):
    _patched_httpx(monkeypatch, _generation_handler("gen-2"))
    monkeypatch.setattr(
        evidence_service,
        "get_cached_graph_with_generation",
        lambda repo_id: ("gen-1", _graph_with_edge()),
    )

    with pytest.raises(HTTPException) as exc_info:
        asyncio.run(
            evidence_service.run_trace_evidence(
                "repo-x",
                "a.py#foo",
                {"CALL"},
                direction="forward",
                requested_max_depth=6,
                server_max_depth=6,
                max_nodes=300,
            )
        )
    assert exc_info.value.status_code == 409


def test_trace_evidence_generation_changed_after_work_is_409(monkeypatch):
    """The generation check before and after the (synchronous) workflow
    disagree -- a rebuild raced the request -- and must be surfaced, not
    silently ignored."""
    calls = {"n": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith("/generation"):
            calls["n"] += 1
            gen = "gen-1" if calls["n"] == 1 else "gen-2"
            return httpx.Response(
                200, json={"ingestion_id": gen, "generation_status": "ready"}
            )
        return httpx.Response(404)

    _patched_httpx(monkeypatch, handler)
    monkeypatch.setattr(
        evidence_service,
        "get_cached_graph_with_generation",
        lambda repo_id: ("gen-1", _graph_with_edge()),
    )

    with pytest.raises(HTTPException) as exc_info:
        asyncio.run(
            evidence_service.run_trace_evidence(
                "repo-x",
                "a.py#foo",
                {"CALL"},
                direction="forward",
                requested_max_depth=6,
                server_max_depth=6,
                max_nodes=300,
            )
        )
    assert exc_info.value.status_code == 409


def test_impact_evidence_happy_path(monkeypatch):
    _patched_httpx(monkeypatch, _generation_handler("gen-1"))
    monkeypatch.setattr(
        evidence_service,
        "get_cached_graph_with_generation",
        lambda repo_id: ("gen-1", _graph_with_edge()),
    )

    result = asyncio.run(
        evidence_service.run_impact_evidence(
            "repo-x", "b.py#bar", max_depth=4, max_candidates=300
        )
    )
    assert result.assessment.status == "satisfied"


# --- Stage A4: explanation phase ---


def test_trace_evidence_with_explanation_query_calls_generate_once(monkeypatch):
    generate_calls = []

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith("/generation"):
            return httpx.Response(
                200, json={"ingestion_id": "gen-1", "generation_status": "ready"}
            )
        if request.url.path.endswith("/generate"):
            generate_calls.append(request)
            return httpx.Response(
                200,
                json={
                    "response": "b.py#bar is reachable from a.py#foo via CALL.",
                    "model": "llama3",
                    "model_alias": "default",
                    "fallback_from": None,
                },
            )
        return httpx.Response(404)

    _patched_httpx(monkeypatch, handler)
    monkeypatch.setattr(
        evidence_service,
        "get_cached_graph_with_generation",
        lambda repo_id: ("gen-1", _graph_with_edge()),
    )

    result = asyncio.run(
        evidence_service.run_trace_evidence(
            "repo-x",
            "a.py#foo",
            {"CALL"},
            direction="forward",
            requested_max_depth=6,
            server_max_depth=6,
            max_nodes=300,
            required_target="b.py#bar",
            explanation_query="is b.py#bar reachable from a.py#foo?",
        )
    )
    assert len(generate_calls) == 1
    assert result.explanation is not None
    assert result.explanation.answer == "b.py#bar is reachable from a.py#foo via CALL."
    assert result.explanation.model_used == "llama3"


def test_no_explanation_query_never_calls_generate(monkeypatch):
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith("/generation"):
            return httpx.Response(
                200, json={"ingestion_id": "gen-1", "generation_status": "ready"}
            )
        if request.url.path.endswith("/generate"):
            raise AssertionError(
                "must not call /generate when explanation_query is None"
            )
        return httpx.Response(404)

    _patched_httpx(monkeypatch, handler)
    monkeypatch.setattr(
        evidence_service,
        "get_cached_graph_with_generation",
        lambda repo_id: ("gen-1", _graph_with_edge()),
    )

    result = asyncio.run(
        evidence_service.run_trace_evidence(
            "repo-x",
            "a.py#foo",
            {"CALL"},
            direction="forward",
            requested_max_depth=6,
            server_max_depth=6,
            max_nodes=300,
        )
    )
    assert result.explanation is None


def test_ambiguous_start_skips_generation(monkeypatch):
    graph = CodebaseGraph()
    graph.add_node(Node("a.py#foo", "a.py"))
    graph.add_node(Node("a.py#dup", "a.py"))
    graph.add_edge("a.py#foo", "a.py#dup", "CALL")
    graph.add_node(Node("b.py#foo", "b.py"))
    graph.add_node(Node("b.py#dup2", "b.py"))
    graph.add_edge("b.py#foo", "b.py#dup2", "CALL")

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith("/generation"):
            return httpx.Response(
                200, json={"ingestion_id": "gen-1", "generation_status": "ready"}
            )
        if request.url.path.endswith("/generate"):
            raise AssertionError("must not call /generate for an ambiguous start")
        return httpx.Response(404)

    _patched_httpx(monkeypatch, handler)
    monkeypatch.setattr(
        evidence_service,
        "get_cached_graph_with_generation",
        lambda repo_id: ("gen-1", graph),
    )

    result = asyncio.run(
        evidence_service.run_trace_evidence(
            "repo-x",
            "foo",
            {"CALL"},
            direction="forward",
            requested_max_depth=6,
            server_max_depth=6,
            max_nodes=300,
            explanation_query="what does foo do?",
        )
    )
    assert result.assessment.status == "needs_clarification"
    assert result.explanation is not None
    assert result.explanation.answer is None
    assert result.explanation.skipped_reason is not None
