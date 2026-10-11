"""Characterize discovery independently of any real repository's answers."""

import asyncio
import json

import httpx
import pytest
from fastapi import HTTPException

from rag_orchestrator.src.retrieval import codebase_utils
from rag_orchestrator.src.retrieval.codebase_queries import CodebaseGraph, Node
from src.core.service import hybrid_retrieve

pytestmark = pytest.mark.unit
TARGET = "pkg/engine.py#Engine.execute"
SEED = "pkg/cli.py#launch"
EXTERNAL = "EXTERNAL_SYMBOL:engine.execute"


def replay(monkeypatch, reference, *, reachable=False, ambiguous=False, stale=False):
    graph = CodebaseGraph()
    identities = [SEED, TARGET, EXTERNAL]
    if ambiguous:
        identities.append("backup/engine.py#Engine.execute")
    for cid in identities:
        graph.add_node(Node(cid, cid))
    graph.add_edge(SEED, TARGET if reachable else EXTERNAL, "CALL")
    lookups = []
    fetched = []
    generation_reads = []

    def backend(request):
        payload = json.loads(request.content) if request.content else {}
        if request.url.path.endswith("/generation"):
            generation_reads.append(True)
            return httpx.Response(200, json={
                "generation_status": "ready",
                "ingestion_id": "g2" if stale and len(generation_reads) > 1 else "g1",
            })
        if request.url.path.endswith("/vectors/search"):
            assert payload["metadata_filter"]["ingestion_id"] == "g1"
            assert payload["metadata_filter"]["repo_id"] == "synthetic"
            return httpx.Response(200, json={"results": [{
                "document_id": SEED, "chunk_id": "seed", "text": "launch",
                "score": 0.9, "metadata": {"canonical_id": SEED},
            }]})
        if request.url.path.endswith("/nodes/lookup"):
            lookups.extend(payload["canonical_ids"])
            return httpx.Response(200, json={"nodes": [
                {"canonical_id": cid, "document_id": cid}
                for cid in payload["canonical_ids"] if cid in identities
            ]})
        if request.url.path.endswith("/search-by-doc"):
            assert payload["ingestion_id"] == "g1"
            fetched.append(payload["document_id"])
            return httpx.Response(200, json={"results": [{
                "chunk_id": f"passage:{payload['document_id']}",
                "text": "implementation passage", "score": 0.5, "metadata": {},
            }]})
        return httpx.Response(404)

    real_client = httpx.AsyncClient

    def client(*args, **kwargs):
        kwargs["transport"] = httpx.MockTransport(backend)
        return real_client(*args, **kwargs)

    monkeypatch.setattr(httpx, "AsyncClient", client)
    monkeypatch.setattr(codebase_utils, "get_cached_graph", lambda _: graph)
    result = asyncio.run(hybrid_retrieve(
        query=f"Trace calls from launch through {reference}.",
        repo_id="synthetic", query_embedding=[0.0] * 8, top_k=10,
        trace_canonical_ids={TARGET},
    ))
    return result, lookups, fetched


@pytest.mark.parametrize("reference,ambiguous", [
    (TARGET, False), ("Engine.execute", False), ("Engine.execute", True),
    ("Missing.execute", False),
])
def test_explicit_reference_does_not_seed_disconnected_indexed_method(
    monkeypatch, reference, ambiguous,
):
    (_, plan), lookups, fetched = replay(
        monkeypatch, reference, ambiguous=ambiguous,
    )
    assert TARGET not in lookups
    assert TARGET not in fetched
    entry = plan["_evidence_trace_partial"][0]
    assert entry["found_by_vector"] is False
    assert entry["found_by_graph"] is False
    assert entry["drop_reason"] == "not_found_by_vector_or_graph"


def test_resolved_call_edge_reaches_the_same_indexed_method(monkeypatch):
    (_, plan), lookups, fetched = replay(monkeypatch, TARGET, reachable=True)
    assert TARGET in lookups
    assert TARGET in fetched
    entry = plan["_evidence_trace_partial"][0]
    assert entry["found_by_graph"] is True
    assert entry["chunk_fetched"] is True


def test_generation_change_aborts_even_when_exact_method_is_reached(monkeypatch):
    with pytest.raises(HTTPException) as error:
        replay(monkeypatch, TARGET, reachable=True, stale=True)
    assert error.value.status_code == 409
