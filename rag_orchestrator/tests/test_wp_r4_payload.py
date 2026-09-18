"""WP-R4 acceptance at the actual outgoing /generate JSON boundary."""
import asyncio
import hashlib
import json

import httpx
import pytest
from fastapi import HTTPException

from src.core import service, simple_service
from rag_orchestrator.src.retrieval import codebase_utils
from src.retrieval.codebase_queries import CodebaseGraph, Node

pytestmark = pytest.mark.unit


class Backend:
    def __init__(self, change_generation=False):
        self.payload = None
        self.fetches = []
        self.generation_checks = 0
        self.change_generation = change_generation

    def __call__(self, request):
        path = request.url.path
        if path.endswith("/generation"):
            self.generation_checks += 1
            generation = "g2" if (
                self.change_generation and self.generation_checks > 1
            ) else "g1"
            return httpx.Response(200, json={
                "ingestion_id": generation, "generation_status": "ready",
            })
        if path == "/v1/vectors/search":
            return httpx.Response(200, json={"results": [{
                "document_id": "seed", "chunk_id": "head",
                "text": "function header", "score": 0.8,
                "metadata": {"canonical_id": "module.py", "chunk_index": 0},
            }]})
        if path.endswith("/nodes/lookup"):
            cids = json.loads(request.content)["canonical_ids"]
            return httpx.Response(200, json={"nodes": [
                {"canonical_id": cid,
                 "document_id": "seed" if cid == "module.py" else cid}
                for cid in cids
            ]})
        if path == "/v1/vectors/search-by-doc":
            body = json.loads(request.content)
            self.fetches.append(body)
            doc = body["document_id"]
            text = "TAIL_EVIDENCE" if doc == "seed" else "EXPANDED_EVIDENCE"
            return httpx.Response(200, json={"results": [{
                "document_id": doc, "chunk_id": doc + "-tail",
                "text": text, "score": 0.95,
                "metadata": {"canonical_id": doc, "chunk_index": 97},
            }]})
        if path == "/generate":
            self.payload = json.loads(request.content)
            return httpx.Response(200, json={
                "response": "ok", "model": "test-model", "fallback_from": "test",
            })
        return httpx.Response(404)


def patch_pipeline(monkeypatch, backend):
    client = httpx.AsyncClient
    monkeypatch.setattr(httpx, "AsyncClient", lambda **kw: client(
        **kw, transport=httpx.MockTransport(backend),
    ))
    for module in [service, simple_service]:
        monkeypatch.setattr(module, "get_embedder", lambda **kw: object())
        monkeypatch.setattr(module, "embed_query", lambda *a: [1.0, 0.0])

    async def resolve(repo_id):
        return repo_id
    monkeypatch.setattr(service, "resolve_repo_id_http", resolve)
    graph = CodebaseGraph()
    graph.add_node(Node("module.py", "module.py"))
    for cid in [*(f"a{i:02}" for i in range(30)), "z_target"]:
        graph.add_node(Node(cid, cid))
        graph.add_edge("module.py", cid, "DEFINES")
    monkeypatch.setattr(codebase_utils, "get_cached_graph", lambda repo: graph)


def test_tail_supplementation_and_same_relation_overload_cross_prompt(monkeypatch):
    backend = Backend()
    patch_pipeline(monkeypatch, backend)
    result = asyncio.run(service.run_rag(
        "explain target", repo_id="repo", max_total_tokens=10000,
    ))
    assert backend.payload is not None
    assert "TAIL_EVIDENCE" in backend.payload["context"]
    assert "[Source: z_target]" in backend.payload["context"]
    assert all(fetch["query_vector"] == [1.0, 0.0] for fetch in backend.fetches)
    assert all(fetch["ingestion_id"] == "g1" for fetch in backend.fetches)
    assert len(backend.fetches) == service.get_settings().MAX_EXPANDED_DOCS + 1
    manifest = result.retrieval_plan["final_context_manifest"]
    assert result.sources == list(dict.fromkeys(
        row["source_label"] for row in manifest
    ))
    texts = {"head": "function header"}
    texts.update({fetch["document_id"] + "-tail": (
        "TAIL_EVIDENCE" if fetch["document_id"] == "seed" else "EXPANDED_EVIDENCE"
    ) for fetch in backend.fetches})
    assert backend.payload["context"] == "\n\n".join(
        f"[Source: {row['source_label']}]\n{texts[row['chunk_id']]}"
        for row in manifest
    )
    assert all(row["text_sha256"] == hashlib.sha256(
        texts[row["chunk_id"]].encode("utf-8")
    ).hexdigest() for row in manifest)
    assert any(row["chunk_index"] == 97 for row in manifest)
    assert result.model_used == "test-model"
    assert result.fallback_from == "test"


def test_generation_change_prevents_generation_call(monkeypatch):
    backend = Backend(change_generation=True)
    patch_pipeline(monkeypatch, backend)
    with pytest.raises(HTTPException) as raised:
        asyncio.run(service.run_rag("target", repo_id="repo"))
    assert raised.value.status_code == 409
    assert backend.payload is None


def test_simple_expansion_and_sources_match_payload(monkeypatch):
    backend = Backend()
    patch_pipeline(monkeypatch, backend)

    def expand(**kwargs):
        plan = kwargs["plan"]
        plan.expanded_document_ids.add("child")
        return plan
    monkeypatch.setattr(simple_service, "expand_retrieval_plan", expand)
    result = asyncio.run(simple_service.run_simple_rag("target"))
    assert backend.payload is not None
    assert "[Source: child]\nEXPANDED_EVIDENCE" in backend.payload["context"]
    assert result.sources == list(dict.fromkeys(
        row["source_label"] for row in result.final_context_manifest
    ))
    assert "child" in result.sources


def test_reranker_loss_is_distinct_from_chunk_and_budget_loss(monkeypatch):
    backend = Backend()
    patch_pipeline(monkeypatch, backend)
    monkeypatch.setattr(service, "rerank_chunks", lambda q, chunks, **kw: [
        chunk for chunk in chunks if chunk["document_id"] == "seed"
    ])
    result = asyncio.run(service.run_rag(
        "target", repo_id="repo", rerank=True, trace_canonical_ids={"z_target"},
    ))
    entry = result.retrieval_plan["evidence_trace"][0]
    assert entry["survives_chunk_limits"] is True
    assert entry["survives_rerank"] is False
    assert entry["drop_reason"] == "dropped_by_reranker"


def test_empty_budget_has_no_sources_or_manifest_claims(monkeypatch):
    backend = Backend()
    patch_pipeline(monkeypatch, backend)
    result = asyncio.run(service.run_rag(
        "target", repo_id="repo", max_total_tokens=0,
    ))
    assert backend.payload["context"] == ""
    assert result.sources == []
    assert result.retrieval_plan["final_context_manifest"] == []
