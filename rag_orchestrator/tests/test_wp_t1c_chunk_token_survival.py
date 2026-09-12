# rag_orchestrator/tests/test_wp_t1c_chunk_token_survival.py
"""
WP-T1c (issue #100): close the two real gaps in the evidence-survival
model left after WP-T1a/T1b --

  1. chunk-index-level detail on /search-by-doc fetches (which indices
     were requested vs. actually returned/kept, post cross-document
     dedup).
  2. survives_chunk_limits (execute_retrieval_plan's per-document slice +
     prepare_chunks_for_agent's max_chunks_per_doc/max_total_chunks) is
     now a distinct field from reaches_final_context (which now runs
     strictly after build_labeled_context's token-budget truncation,
     instead of before it, per the 2026-09-07 audit's finding that the
     old reaches_final_context only ever measured chunk-count survival).

A candidate can pass chunk-count limits and still be dropped by the
token budget -- this file constructs exactly that case and asserts the
two fields disagree, which was impossible to observe before this WP.

No ranking/cap/fetch/graph-expansion behavior change: test_expansion_caps.py,
test_evidence_survival.py, test_wp_t1a_evidence_model.py, and
test_wp_t1b_trace_identity.py already cover that and must keep passing
unchanged (test_evidence_survival.py's two finalize_evidence_survival call
sites were updated for the new two-set signature, since evolving that
exact contract is this WP's job -- see the WP-T1c commit).
"""
import asyncio
import json

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
    """Seed doc has one long chunk that alone exceeds the token budget,
    so the expanded doc's chunk survives chunk-count limits (both docs
    fit under MAX_TOTAL_CHUNKS) but is dropped by the token budget."""

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
                            "text": " ".join(["word"] * 20),
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
                        },
                        {
                            "chunk_id": f"second-chunk-of-{doc_id}",
                            "text": "a second chunk for the same document",
                            "score": 0.4,
                            "metadata": {},
                        },
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


def _run_hybrid(monkeypatch):
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
        )
    )


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


# ------------------------------------------------------------------
# 1. Chunk-index-level detail on /search-by-doc fetches
# ------------------------------------------------------------------


def test_hybrid_retrieve_reports_requested_and_returned_chunk_indices(monkeypatch):
    from src.core.config import get_settings

    _, plan = _run_hybrid(monkeypatch)

    requested = plan["chunks_requested_by_document"]["helper-doc"]
    assert requested == list(range(get_settings().EXPANDED_DOC_CHUNKS))

    returned = plan["chunks_returned_by_document"]["helper-doc"]
    assert returned == [0, 1]


def test_retrieved_chunk_carries_its_index(monkeypatch):
    chunks_by_doc, _ = _run_hybrid(monkeypatch)
    helper_chunks = chunks_by_doc["helper-doc"]
    assert [c.chunk_index for c in helper_chunks] == [0, 1]


# ------------------------------------------------------------------
# 2. survives_chunk_limits and reaches_final_context are distinct
# ------------------------------------------------------------------


def test_chunk_limits_and_token_budget_are_tracked_separately_in_retrieval_plan(
    monkeypatch,
):
    result = _run_rag(monkeypatch, max_total_tokens=15)

    plan = result.retrieval_plan
    assert "tokens_before_budget" in plan
    assert "tokens_after_budget" in plan
    # The seed chunk (20 words) alone exceeds the 15-token budget, so
    # strictly less made it through the token budget than was available
    # after chunk-count limits.
    assert plan["tokens_after_budget"] <= 15
    assert plan["tokens_before_budget"] > plan["tokens_after_budget"]


def test_survives_chunk_limits_can_be_true_while_reaches_final_context_is_false(
    monkeypatch,
):
    """The exact failure mode WP-T1c exists to surface: a document passes
    chunk-count limits (small MAX_TOTAL_CHUNKS-style truncation) but is
    then dropped by a tight token budget -- the two fields must disagree
    here, which the pre-WP-T1c single reaches_final_context flag could
    never express."""
    result = _run_rag(
        monkeypatch,
        max_total_tokens=15,
        trace_canonical_ids={"helper.py#helper"},
    )

    entries = {
        e["canonical_id"]: e for e in result.retrieval_plan["evidence_trace"]
    }
    entry = entries["helper.py#helper"]
    assert entry["survives_chunk_limits"] is True
    assert entry["reaches_final_context"] is False


def test_survives_chunk_limits_and_reaches_final_context_both_true_with_ample_budget(
    monkeypatch,
):
    result = _run_rag(
        monkeypatch,
        max_total_tokens=4096,
        trace_canonical_ids={"helper.py#helper"},
    )

    entries = {
        e["canonical_id"]: e for e in result.retrieval_plan["evidence_trace"]
    }
    entry = entries["helper.py#helper"]
    assert entry["survives_chunk_limits"] is True
    assert entry["reaches_final_context"] is True
