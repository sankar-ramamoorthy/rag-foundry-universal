# rag_orchestrator/tests/test_wp_t1b_trace_identity.py
"""
WP-T1b (issue #100): one trace_id per /v1/rag request, threaded through
hybrid_retrieve, plus structured-ish stage-event log lines that all carry
it -- so a single request's retrieval pipeline can be reconstructed by
grepping for one ID, instead of by hand from unrelated log lines.

Deliberately plain `logging` (see service._log_stage's docstring): this
test asserts against caplog text, not a JSON/structured-logging schema,
matching WP-T1's explicit non-goal of adopting structlog/OpenTelemetry in
this work package.

No ranking/cap/fetch/chunk-selection behavior change: test_expansion_caps.py,
test_evidence_survival.py, and test_wp_t1a_evidence_model.py already cover
that and must keep passing unchanged.
"""
import asyncio
import json
import logging

import httpx
import pytest

from rag_orchestrator.src.retrieval import codebase_utils
from src.core.service import hybrid_retrieve, run_rag
from src.retrieval.codebase_queries import CodebaseGraph, Node

pytestmark = pytest.mark.unit


def _build_graph() -> CodebaseGraph:
    graph = CodebaseGraph()
    graph.add_node(Node("module.py", "module.py"))
    graph.add_node(Node("helper.py#helper", "helper.py"))
    graph.add_edge("module.py", "helper.py#helper", "DEFINES")
    return graph


class FakeBackend:
    def __call__(self, request: httpx.Request) -> httpx.Response:
        path = request.url.path

        if path == "/v1/vectors/search":
            return httpx.Response(
                200,
                json={
                    "results": [
                        {
                            "document_id": "module-doc",
                            "chunk_id": "module-chunk-0",
                            "text": "module docstring/header",
                            "score": 0.9,
                            "metadata": {
                                "canonical_id": "module.py",
                                "repo_id": "repo-x",
                            },
                        }
                    ]
                },
            )

        if path.startswith("/v1/graph/repos/"):
            nodes = [
                {"canonical_id": "module.py", "document_id": "module-doc"},
                {"canonical_id": "helper.py#helper", "document_id": "helper-doc"},
            ]
            return httpx.Response(200, json={"nodes": nodes})

        if path == "/v1/vectors/search-by-doc":
            doc_id = json.loads(request.content)["document_id"]
            return httpx.Response(
                200,
                json={
                    "results": [
                        {
                            "chunk_id": f"chunk-of-{doc_id}",
                            "text": f"implementation of {doc_id}",
                            "score": 0.5,
                            "metadata": {},
                        }
                    ]
                },
            )

        if path == "/generate":
            return httpx.Response(200, json={"response": "ok"})

        return httpx.Response(404)


def _patched_client(backend):
    real_async_client = httpx.AsyncClient

    def patched(*args, **kwargs):
        kwargs["transport"] = httpx.MockTransport(backend)
        return real_async_client(*args, **kwargs)

    return patched


def _run_hybrid(monkeypatch, **kwargs):
    monkeypatch.setattr(httpx, "AsyncClient", _patched_client(FakeBackend()))
    monkeypatch.setattr(
        codebase_utils, "get_cached_graph", lambda repo_id: _build_graph()
    )
    return asyncio.run(
        hybrid_retrieve(
            query="explain the module",
            repo_id="repo-x",
            query_embedding=[0.0] * 8,
            top_k=5,
            **kwargs,
        )
    )


def _run_rag(monkeypatch):
    monkeypatch.setattr(httpx, "AsyncClient", _patched_client(FakeBackend()))
    monkeypatch.setattr(
        codebase_utils, "get_cached_graph", lambda repo_id: _build_graph()
    )

    async def fake_resolve_repo_id(repo_id):
        return repo_id or "repo-x"

    monkeypatch.setattr(
        "src.core.service.resolve_repo_id_http", fake_resolve_repo_id
    )
    monkeypatch.setattr(
        "src.core.service.embed_query", lambda query, embedder: [0.0] * 8
    )
    monkeypatch.setattr("src.core.service.get_embedder", lambda **kwargs: object())

    return asyncio.run(run_rag(query="explain the module", repo_id="repo-x"))


# ------------------------------------------------------------------
# 1. Every request gets one trace_id
# ------------------------------------------------------------------


def test_hybrid_retrieve_generates_a_trace_id_when_omitted(monkeypatch):
    _, plan = _run_hybrid(monkeypatch)
    assert plan["trace_id"]


def test_two_hybrid_retrieve_calls_get_different_trace_ids(monkeypatch):
    _, plan_a = _run_hybrid(monkeypatch)
    _, plan_b = _run_hybrid(monkeypatch)
    assert plan_a["trace_id"] != plan_b["trace_id"]


def test_hybrid_retrieve_uses_the_caller_supplied_trace_id(monkeypatch):
    _, plan = _run_hybrid(monkeypatch, trace_id="fixed-trace-id")
    assert plan["trace_id"] == "fixed-trace-id"


def test_run_rag_result_carries_a_trace_id(monkeypatch):
    result = _run_rag(monkeypatch)
    assert result.trace_id


def test_run_rag_result_trace_id_matches_retrieval_plan_trace_id(monkeypatch):
    """The same trace_id must connect RAGResult.trace_id and the
    retrieval_plan dict's trace_id -- both are views onto the same
    request, not independently generated IDs."""
    result = _run_rag(monkeypatch)
    assert result.trace_id == result.retrieval_plan["trace_id"]


# ------------------------------------------------------------------
# 2. Stage-event log lines all carry that same trace_id
# ------------------------------------------------------------------


def test_run_rag_stage_events_all_carry_the_same_trace_id(monkeypatch, caplog):
    with caplog.at_level(logging.INFO, logger="src.core.service"):
        result = _run_rag(monkeypatch)

    stage_lines = [
        record.message
        for record in caplog.records
        if "stage=" in record.message
    ]
    expected_stages = {
        "rag.query.started",
        "retrieval.seed.completed",
        "graph.expand.completed",
        "expansion.cap.applied",
        "chunks.fetch.completed",
        "llm.generate.completed",
        "rag.query.completed",
    }
    seen_stages = {
        line.split("stage=")[1].split(" ")[0] for line in stage_lines
    }
    assert expected_stages <= seen_stages

    for line in stage_lines:
        assert f"trace_id={result.trace_id}" in line
