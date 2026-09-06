# rag_orchestrator/tests/test_evidence_survival.py
"""
Issue #89 regression fixture, modeled on the confirmed runtime failure in
DOCS/test_results/2026-09-03-rag-retrieval-quality-linux-tailscale-baseline.md
(section 13, "Runtime Root-Cause Confirmation"):

    graph expansion correctly discovers exact helper-function documents
    (_compiled_query, _language_for, _parser_for at ranks 25-27), but
    authority-blind expanded ranking places them below the fixed
    MAX_EXPANDED_DOCS=20 cutoff, so they are discarded before
    /search-by-doc ever fetches them and their implementation text never
    reaches the LLM prompt.

This reproduces that shape (one seed module, N children ranked purely by
canonical_id since they're all one graph-hop from the same seed, three of
them landing past the cap) using the same fake-backend harness as
test_expansion_caps.py, and asserts the evidence_trace instrumentation
(rag_orchestrator/src/retrieval/evidence_trace.py) surfaces exactly that
failure — before any ranking/cap fix is attempted, per issue #89's ordering.
"""
import asyncio
import json

import httpx
import pytest

from rag_orchestrator.src.retrieval import codebase_utils
from rag_orchestrator.src.retrieval.evidence_trace import (
    DROP_TRUNCATED_BY_CAP,
    finalize_evidence_survival,
)
from src.core.config import get_settings
from src.core.service import hybrid_retrieve
from src.retrieval.codebase_queries import CodebaseGraph, Node

pytestmark = pytest.mark.unit

N_CHILDREN = 30  # matches the diagnostic's 59-considered/20-used shape closely
# enough: MAX_EXPANDED_DOCS=20 default, ranks 25-27 land past the cap either way.
HELPER_CANONICAL_IDS = {"n25", "n26", "n27"}


def _build_graph() -> CodebaseGraph:
    """One module ("module.py") DEFINES N_CHILDREN helper functions,
    mirroring treesitter/base.py DEFINES _language_for/_parser_for/etc."""
    graph = CodebaseGraph()
    graph.add_node(Node("module.py", "module.py"))
    for i in range(N_CHILDREN):
        cid = f"n{i:02d}"
        graph.add_node(Node(cid, f"module.py#{cid}"))
        graph.add_edge("module.py", cid, "DEFINES")
    return graph


class FakeBackend:
    def __init__(self):
        self.search_by_doc_docs = []

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
            nodes = [{"canonical_id": "module.py", "document_id": "module-doc"}]
            nodes += [
                {"canonical_id": f"n{i:02d}", "document_id": f"n{i:02d}-doc"}
                for i in range(N_CHILDREN)
            ]
            return httpx.Response(200, json={"nodes": nodes})

        if path == "/v1/vectors/search-by-doc":
            doc_id = json.loads(request.content)["document_id"]
            self.search_by_doc_docs.append(doc_id)
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

        return httpx.Response(404)


def _run_hybrid(monkeypatch, backend, trace_canonical_ids=None):
    real_async_client = httpx.AsyncClient

    def patched_client(*args, **kwargs):
        kwargs["transport"] = httpx.MockTransport(backend)
        return real_async_client(*args, **kwargs)

    monkeypatch.setattr(httpx, "AsyncClient", patched_client)
    monkeypatch.setattr(
        codebase_utils, "get_cached_graph", lambda repo_id: _build_graph()
    )

    return asyncio.run(
        hybrid_retrieve(
            query="what does the module define?",  # routes to traverse_defines
            repo_id="repo-x",
            query_embedding=[0.0] * 8,
            top_k=5,
            trace_canonical_ids=trace_canonical_ids,
        )
    )


def test_helper_functions_are_found_by_graph_but_truncated_by_cap(monkeypatch):
    """Confirms the regression: graph expansion finds the helpers (rank
    25-27), but they don't survive MAX_EXPANDED_DOCS and are never fetched."""
    backend = FakeBackend()
    _, plan = _run_hybrid(
        monkeypatch, backend, trace_canonical_ids=HELPER_CANONICAL_IDS
    )

    cap = get_settings().MAX_EXPANDED_DOCS
    trace = {e["canonical_id"]: e for e in plan["_evidence_trace_partial"]}

    assert set(trace) == HELPER_CANONICAL_IDS
    for cid in HELPER_CANONICAL_IDS:
        entry = trace[cid]
        assert entry["found_by_vector"] is False
        assert entry["found_by_graph"] is True
        assert entry["expanded_rank"] >= cap  # ranks 25, 26, 27 >= cap (20)
        assert entry["survives_cap"] is False
        assert entry["chunk_fetched"] is False
        assert entry["drop_reason"] == DROP_TRUNCATED_BY_CAP

    # Independently confirms none of the helper docs were ever fetched.
    fetched_docs = set(backend.search_by_doc_docs)
    assert fetched_docs.isdisjoint({f"{cid}-doc" for cid in HELPER_CANONICAL_IDS})


def test_helper_functions_never_reach_final_context(monkeypatch):
    """End-to-end shape of the diagnostic's conclusion: even after final
    context assembly, the helper implementations are absent — only the
    module's own (unrelated) seed chunk survives."""
    backend = FakeBackend()
    _, plan = _run_hybrid(
        monkeypatch, backend, trace_canonical_ids=HELPER_CANONICAL_IDS
    )

    # Simulates run_rag's post-prepare_chunks_for_agent finalization: only
    # the seed module document made it into the final prompt.
    final_document_ids = {"module-doc"}
    finalized = finalize_evidence_survival(
        plan["_evidence_trace_partial"], final_document_ids
    )

    assert len(finalized) == 3
    for entry in finalized:
        assert entry["reaches_final_context"] is False
        # already dropped at the cap stage; final-context check must not
        # overwrite the more specific reason.
        assert entry["drop_reason"] == DROP_TRUNCATED_BY_CAP


def test_no_trace_requested_costs_nothing(monkeypatch):
    """Default production call path: trace_canonical_ids omitted, plan dict
    carries no evidence_trace key at all."""
    backend = FakeBackend()
    _, plan = _run_hybrid(monkeypatch, backend, trace_canonical_ids=None)

    assert "_evidence_trace_partial" not in plan
    assert "evidence_trace" not in plan
