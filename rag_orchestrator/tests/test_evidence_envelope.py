# rag_orchestrator/tests/test_evidence_envelope.py
"""
Issue #406 / specs/011-evidence-envelope: every evidence-bearing response
carries an additive `envelope` (schema_version, repo_id, generation_id,
commit_sha, coverage, limitations). Mocked httpx and a patched graph cache;
no network, database or model.
"""

import asyncio

import httpx
import pytest
from fastapi.testclient import TestClient

from src.api.v1.main import app
from src.core import envelope as envelope_module
from src.core import evidence_service
from src.core.service import RAGResult
from src.retrieval.codebase_queries import CodebaseGraph, Node

pytestmark = pytest.mark.unit

GEN = "00000000-0000-4000-8000-000000000001"
SHA = "a" * 40


def _patched_client(monkeypatch, handler):
    real = httpx.AsyncClient

    def patched(*args, **kwargs):
        kwargs["transport"] = httpx.MockTransport(handler)
        return real(*args, **kwargs)

    monkeypatch.setattr(httpx, "AsyncClient", patched)


def _commit_lookup(monkeypatch, commit=SHA, notes=()):
    async def fake(repo_id, generation_id):
        return commit, list(notes)

    monkeypatch.setattr(envelope_module, "fetch_commit_sha", fake)


# --- fetch_commit_sha (the one lookup) ---


def _lookup(monkeypatch, body, status=200):
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/v1/repos/repo-x/generation"
        return httpx.Response(status, json=body)

    _patched_client(monkeypatch, handler)
    return asyncio.run(envelope_module._real_fetch_commit_sha("repo-x", GEN))


def test_commit_found_for_same_generation(monkeypatch):
    commit, notes = _lookup(
        monkeypatch,
        {"ingestion_id": GEN, "generation_status": "ready", "commit_sha": SHA},
    )
    assert (commit, notes) == (SHA, [])


def test_commit_null_when_generation_recorded_none(monkeypatch):
    commit, notes = _lookup(
        monkeypatch,
        {"ingestion_id": GEN, "generation_status": "ready", "commit_sha": None},
    )
    assert commit is None
    assert any("not recorded" in n for n in notes)


def test_commit_null_when_generation_changed(monkeypatch):
    commit, notes = _lookup(
        monkeypatch,
        {"ingestion_id": "other", "generation_status": "ready", "commit_sha": SHA},
    )
    assert commit is None
    assert any("changed" in n for n in notes)


def test_commit_lookup_failure_never_raises(monkeypatch):
    commit, notes = _lookup(monkeypatch, {"detail": "boom"}, status=500)
    assert commit is None
    assert any("lookup failed" in n for n in notes)


# --- coverage rules ---


def test_rag_coverage_rules():
    f = envelope_module.rag_coverage
    assert f({"generation_id": GEN})[0] == "partial"
    assert f({})[0] == "unknown"
    complete = {
        "generation_id": GEN,
        "strategy": "python_inventory",
        "completion": "verified_complete",
    }
    assert f(complete)[0] == "complete"
    limited = {**complete, "completion": "budget_limited"}
    assert f(limited)[0] == "partial"
    other = {**complete, "completion": "incomplete"}
    assert f(other)[0] == "unknown"


# --- orient ---


def _orient_body(gaps=()):
    return {
        "repo_id": "repo-x",
        "ingestion_id": GEN,
        "generation_status": "ready",
        "commit_sha": SHA,
        "languages": {"python": 3},
        "file_counts": {"indexed": 3, "non_indexed": 0, "total": 3},
        "manifests": [],
        "services": [],
        "test_dirs": [],
        "docs_dirs": [],
        "heuristic_fields": ["test_dirs"],
        "gaps": list(gaps),
        "computed_at": None,
    }


def _orient(monkeypatch, body):
    _patched_client(monkeypatch, lambda request: httpx.Response(200, json=body))
    return TestClient(app).get("/v1/repos/repo-x/orient")


def test_orient_envelope_uses_body_generation_and_commit(monkeypatch):
    body = _orient_body()
    response = _orient(monkeypatch, body)
    assert response.status_code == 200
    out = response.json()
    env = out.pop("envelope")
    assert out == body  # every previous field is unchanged
    assert env["schema_version"] == "1"
    assert env["repo_id"] == "repo-x"
    assert env["generation_id"] == GEN
    assert env["commit_sha"] == SHA
    assert env["coverage"] == "complete"


def test_orient_gaps_make_coverage_partial_and_are_listed(monkeypatch):
    gaps = [{"category": "services", "path": None, "reason": "no compose file"}]
    env = _orient(monkeypatch, _orient_body(gaps)).json()["envelope"]
    assert env["coverage"] == "partial"
    assert any("no compose file" in lim for lim in env["limitations"])


def test_orient_null_commit_is_stated(monkeypatch):
    body = {**_orient_body(), "commit_sha": None}
    env = _orient(monkeypatch, body).json()["envelope"]
    assert env["commit_sha"] is None
    assert any("not recorded" in lim for lim in env["limitations"])


# --- trace and impact ---


def _graph() -> CodebaseGraph:
    graph = CodebaseGraph()
    graph.add_node(Node("a.py#foo", "a.py"))
    graph.add_node(Node("b.py#bar", "b.py"))
    graph.add_edge("a.py#foo", "b.py#bar", "CALL")
    return graph


def _patch_graph(monkeypatch):
    import src.retrieval.codebase_utils as codebase_utils

    monkeypatch.setattr(
        codebase_utils,
        "get_cached_graph_with_generation",
        lambda repo_id, force_reload=False: (GEN, _graph()),
    )


def test_trace_envelope(monkeypatch):
    _patch_graph(monkeypatch)
    _commit_lookup(monkeypatch)
    response = TestClient(app).get(
        "/v1/repos/repo-x/trace", params={"start": "a.py#foo"}
    )
    body = response.json()
    env = body["envelope"]
    assert env["generation_id"] == GEN == body["ingestion_id"]
    assert env["commit_sha"] == SHA
    assert env["coverage"] == "complete"
    assert any("runtime" in lim for lim in env["limitations"])


def test_trace_depth_limit_makes_coverage_partial(monkeypatch):
    _patch_graph(monkeypatch)
    _commit_lookup(monkeypatch)
    body = TestClient(app).get(
        "/v1/repos/repo-x/trace", params={"start": "a.py#foo", "max_depth": 1}
    ).json()
    if body["truncated"] or body["depth_limited"]:
        assert body["envelope"]["coverage"] == "partial"
    else:
        assert body["envelope"]["coverage"] == "complete"


def test_impact_envelope(monkeypatch):
    _patch_graph(monkeypatch)
    _commit_lookup(monkeypatch, commit=None, notes=["commit_sha not recorded"])
    body = TestClient(app).get(
        "/v1/repos/repo-x/impact", params={"start": "b.py#bar"}
    ).json()
    env = body["envelope"]
    assert env["generation_id"] == GEN
    assert env["commit_sha"] is None
    assert "commit_sha not recorded" in env["limitations"]
    assert any("runtime" in lim for lim in env["limitations"])


# --- evidence workflow ---


def test_evidence_endpoint_envelope(monkeypatch):
    _commit_lookup(monkeypatch)

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith("/generation"):
            return httpx.Response(
                200, json={"ingestion_id": GEN, "generation_status": "ready"}
            )
        return httpx.Response(200, json=_orient_body())

    _patched_client(monkeypatch, handler)
    response = TestClient(app).post(
        "/v1/repos/repo-x/evidence", json={"mode": "orient"}
    )
    assert response.status_code == 200
    body = response.json()
    env = body["envelope"]
    assert env["generation_id"] == GEN
    assert env["commit_sha"] == SHA
    assert env["coverage"] == {
        "satisfied": "complete",
        "partial": "partial",
        "needs_clarification": "unknown",
    }[body["assessment"]["status"]]
    assert "generation_id" not in body  # not leaked as a loose field


def test_evidence_workflow_result_carries_generation(monkeypatch):
    async def gen(repo_id):
        return GEN

    async def verify(repo_id, expected):
        return None

    async def orient(repo_id):
        return _orient_body()

    monkeypatch.setattr(evidence_service, "_query_generation", gen)
    monkeypatch.setattr(evidence_service, "_verify_generation", verify)
    monkeypatch.setattr(evidence_service, "fetch_orient_response", orient)
    result = asyncio.run(evidence_service.run_orient_evidence("repo-x", []))
    assert result.generation_id == GEN


# --- RAG ---


def _rag_result(plan):
    return RAGResult(
        answer="a", sources=["s"], repo_id="repo-x", retrieval_plan=plan
    )


def _patch_rag(monkeypatch, plan):
    import src.api.v1.routes as routes

    async def no_inventory(query):
        return None

    async def fake_run_rag(**kwargs):
        return _rag_result(plan)

    monkeypatch.setattr(routes, "inventory_response", no_inventory)
    monkeypatch.setattr(routes, "run_rag", fake_run_rag)


def test_rag_envelope_ordinary_retrieval_is_partial(monkeypatch):
    _commit_lookup(monkeypatch)
    _patch_rag(monkeypatch, {"generation_id": GEN})
    response = TestClient(app).post(
        "/v1/rag", json={"query": "q", "repo_id": "repo-x"}
    )
    assert response.status_code == 200
    body = response.json()
    assert body["sources"] == ["s"]  # existing fields unchanged
    env = body["envelope"]
    assert env["generation_id"] == GEN
    assert env["commit_sha"] == SHA
    assert env["coverage"] == "partial"
    assert env["repo_id"] == "repo-x"


def test_rag_envelope_without_generation_is_unknown(monkeypatch):
    _commit_lookup(monkeypatch)
    _patch_rag(monkeypatch, {})
    env = TestClient(app).post(
        "/v1/rag", json={"query": "q", "repo_id": "repo-x"}
    ).json()["envelope"]
    assert env["generation_id"] is None
    assert env["commit_sha"] is None
    assert env["coverage"] == "unknown"
    assert env["limitations"]


def test_rag_inventory_path_gets_envelope(monkeypatch):
    import src.api.v1.routes as routes
    from src.api.v1.models import RAGResponse

    _commit_lookup(monkeypatch)

    async def inventory(query):
        return RAGResponse(
            answer="2 functions",
            sources=["x.py"],
            repo_id="repo-x",
            retrieval_plan={
                "generation_id": GEN,
                "strategy": "python_inventory",
                "completion": "verified_complete",
            },
        )

    monkeypatch.setattr(routes, "inventory_response", inventory)
    env = TestClient(app).post(
        "/v1/rag", json={"query": "What functions are in x.py?", "repo_id": "repo-x"}
    ).json()["envelope"]
    assert env["coverage"] == "complete"
    assert env["generation_id"] == GEN
