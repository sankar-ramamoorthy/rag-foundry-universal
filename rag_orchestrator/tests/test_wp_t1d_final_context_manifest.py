# rag_orchestrator/tests/test_wp_t1d_final_context_manifest.py
"""
WP-T1d (issue #100): a structured pre-LLM-call record of exactly what
crossed into the assembled context -- the hard boundary the WP-T1
planning doc calls "retrieval succeeded only if the needed evidence
crossed this boundary". Built from the same chunk list
build_labeled_context joins (via select_chunks_within_token_budget), so
it can never drift from what the model actually receives.

No ranking/cap/fetch/chunk-selection/token-budget behavior change: this
is a read-only summary of already-computed data, attached to
retrieval_plan_dict (no new API surface). test_expansion_caps.py,
test_evidence_survival.py, and the T1a/T1b/T1c test files already cover
that and must keep passing unchanged.
"""
import asyncio
import json

import httpx
import pytest

from rag_orchestrator.src.retrieval import codebase_utils
from src.core.service import run_rag

pytestmark = pytest.mark.unit


def _build_graph():
    from src.retrieval.codebase_queries import CodebaseGraph, Node

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
                            "text": "helper implementation text",
                            "score": 0.5,
                            "metadata": {"canonical_id": "helper.py#helper"},
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


def _run_rag(monkeypatch, **kwargs):
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

    return asyncio.run(
        run_rag(query="explain the module", repo_id="repo-x", **kwargs)
    )


def test_final_context_manifest_lists_seed_and_expanded_entries(monkeypatch):
    result = _run_rag(monkeypatch, max_total_tokens=4096)

    manifest = result.retrieval_plan["final_context_manifest"]
    by_doc = {entry["document_id"]: entry for entry in manifest}

    assert by_doc["module-doc"]["selection_reason"] == "seed"
    assert by_doc["module-doc"]["canonical_id"] == "module.py"

    assert by_doc["helper-doc"]["selection_reason"] == (
        "expanded via DEFINES from module-doc"
    )
    assert by_doc["helper-doc"]["canonical_id"] == "helper.py#helper"
    assert by_doc["helper-doc"]["chunk_index"] == 0


def test_manifest_entries_have_char_and_token_counts(monkeypatch):
    result = _run_rag(monkeypatch, max_total_tokens=4096)

    manifest = result.retrieval_plan["final_context_manifest"]
    for entry in manifest:
        assert entry["char_count"] > 0
        assert entry["token_count"] > 0
        assert entry["source_label"]


def test_manifest_excludes_chunks_dropped_by_token_budget(monkeypatch):
    """A tight token budget that only fits the seed chunk must not list
    the expanded (helper) chunk in the manifest -- the manifest reflects
    what actually crossed into the LLM prompt, not everything that
    survived chunk-count limits."""
    result = _run_rag(monkeypatch, max_total_tokens=3)

    manifest = result.retrieval_plan["final_context_manifest"]
    document_ids = {entry["document_id"] for entry in manifest}
    assert "helper-doc" not in document_ids


def test_manifest_is_empty_list_when_nothing_fits_budget(monkeypatch):
    result = _run_rag(monkeypatch, max_total_tokens=0)
    assert result.retrieval_plan["final_context_manifest"] == []
