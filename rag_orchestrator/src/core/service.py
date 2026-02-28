# rag_orchestrator/src/core/service.py
# ADR-045 Hybrid Vector + Graph RAG (HTTP-only, clean boundaries)

import logging
from typing import List, Optional, Callable, Dict, Any, Set, cast
import httpx

from fastapi import HTTPException
from pydantic import BaseModel

from src.core.config import get_settings
from shared.embedders.query import embed_query
from shared.embedders.factory import get_embedder

from shared.retrieval.retrieval_plan import RetrievalPlan
from rag_orchestrator.src.retrieval.execute_plan import execute_retrieval_plan
from rag_orchestrator.src.retrieval.agent_adapter import prepare_chunks_for_agent
from rag_orchestrator.src.retrieval.types import RetrievedChunk

from rag_orchestrator.src.retrieval.codebase_utils import extract_canonical_ids_from_chunks
from rag_orchestrator.src.retrieval.traversal_selector import (
    select_traversal_strategies,
    execute_traversals,
)
from rag_orchestrator.src.retrieval.codebase_queries import CodebaseGraph, Node

logger = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO)


# ------------------------------------------------------------------
# Response Model
# ------------------------------------------------------------------

class RAGResult(BaseModel):
    answer: str
    sources: List[str]
    repo_id: str
    retrieval_plan: Dict[str, Any]


# ------------------------------------------------------------------
# REPO RESOLUTION (HTTP via ingestion_service)
# ------------------------------------------------------------------

async def resolve_repo_id_http(repo_id: Optional[str]) -> str:
    """
    Resolve repo_id using ingestion_service /v1/repos endpoint.
    """
    settings = get_settings()
    repos_url = f"{settings.INGESTION_SERVICE_URL}/v1/repos"

    async with httpx.AsyncClient(timeout=30) as client:
        resp = await client.get(repos_url)
        if resp.status_code != 200:
            raise HTTPException(500, "Failed to fetch repositories")

        repos = resp.json()

        # If repo explicitly provided → validate
        if repo_id:
            if any(r["id"] == repo_id for r in repos):
                logger.info(f"Using explicit repo_id: {repo_id[:8]}...")
                return repo_id
            raise HTTPException(404, "Repository not found")

        # Otherwise use first complete repo
        complete = [r for r in repos if r.get("status") == "completed"]
        if complete:
            selected = complete[0]["id"]
            logger.info(f"Using first complete repo: {selected[:8]}...")
            return selected

    raise HTTPException(400, "No complete repositories available")


# ------------------------------------------------------------------
# GRAPH API: canonical_ids → document_ids
# ------------------------------------------------------------------

async def canonical_ids_to_document_ids_http(
    repo_id: str,
    canonical_ids: Set[str],
) -> Set[str]:
    """
    Resolve canonical_ids to document_ids via ingestion_service graph API.
    """
    if not canonical_ids:
        return set()

    settings = get_settings()
    url = f"{settings.INGESTION_SERVICE_URL}/v1/graph/repos/{repo_id}/nodes"
    logger.info(f"url = {url}")
    params = {"canonical_ids": ",".join(sorted(canonical_ids))}

    async with httpx.AsyncClient(timeout=200) as client:
        try:
            resp = await client.get(url, params=params)
            resp.raise_for_status()
            data = resp.json()

            document_ids = {node["document_id"] for node in data.get("nodes", [])}
            logger.info(
                f"Graph API: {len(canonical_ids)} canonical_ids → "
                f"{len(document_ids)} document_ids"
            )
            return document_ids

        except Exception as e:
            logger.warning(f"Graph lookup failed: {e}")
            return set()


# ------------------------------------------------------------------
# HYBRID RETRIEVAL (Vector → Canonical → Graph → Docs → Chunks)
# ------------------------------------------------------------------

async def hybrid_retrieve(
    query: str,
    repo_id: str,
    query_embedding: List[float],
    top_k: int = 20,
) -> tuple[Dict[str, List[RetrievedChunk]], Dict[str, Any]]:
    """
    Implements ADR-045 hybrid retrieval pipeline.

    Returns:
        retrieved_chunks_by_document,
        retrieval_plan_dict
    """
    settings = get_settings()
    logger.info(f"🔄 Hybrid retrieval | repo={repo_id[:8]} | q='{query[:50]}...'")

    search_url = f"{settings.VECTOR_STORE_URL}/v1/vectors/search"
    payload = {"query_vector": query_embedding, "k": top_k,
                "metadata_filter": {"doc_type": "code"}}

    async with httpx.AsyncClient(timeout=200) as client:
        resp = await client.post(search_url, json=payload)
        if resp.status_code != 200 or not resp.json().get("results"):
            logger.info("No code chunks found. Falling back to general search.")
            payload.pop("metadata_filter", None)
            resp = await client.post(search_url, json=payload)
        resp.raise_for_status()
        raw_results = resp.json().get("results", [])

    retrieved_chunks_by_document: Dict[str, List[RetrievedChunk]] = {}
    seed_chunks: List[RetrievedChunk] = []

    for r in raw_results:
        doc_id = r.get("document_id") or r.get("metadata", {}).get("document_id")
        if not doc_id:
            continue
        chunk = RetrievedChunk(
            document_id=doc_id,
            chunk_id=r["chunk_id"],
            text=r["text"],
            score=r.get("score"),
            metadata=r.get("metadata", {}),
        )
        seed_chunks.append(chunk)
        retrieved_chunks_by_document.setdefault(doc_id, []).append(chunk)

    seed_canonical_ids = extract_canonical_ids_from_chunks(seed_chunks)
    logger.info(f"📊 {len(seed_chunks)} chunks → {len(seed_canonical_ids)} canonical_ids")

    expanded_canonical_ids: Set[str] = set()
    if seed_canonical_ids:
        from rag_orchestrator.src.retrieval.codebase_utils import get_cached_graph

        graph: CodebaseGraph = get_cached_graph(repo_id)
        start_cid = max(seed_canonical_ids, key=len)
        strategies = select_traversal_strategies(query, seed_canonical_ids)
        expanded_nodes: List[Node] = execute_traversals(graph, start_cid, strategies)
        expanded_canonical_ids = {node.canonical_id for node in expanded_nodes}

    all_canonical_ids = seed_canonical_ids | expanded_canonical_ids
    all_document_ids = await canonical_ids_to_document_ids_http(repo_id, all_canonical_ids)

    seed_doc_ids = set(retrieved_chunks_by_document.keys())
    missing_doc_ids = all_document_ids - seed_doc_ids

    async with httpx.AsyncClient(timeout=200) as client:
        for doc_id in missing_doc_ids:
            try:
                doc_url = f"{settings.VECTOR_STORE_URL}/v1/vectors/search-by-doc"
                doc_payload = {"document_id": doc_id, "k": 10}
                resp = await client.post(doc_url, json=doc_payload)
                if resp.status_code == 200:
                    for r in resp.json().get("results", []):
                        chunk = RetrievedChunk(
                            document_id=doc_id,
                            chunk_id=r["chunk_id"],
                            text=r["text"],
                            score=r.get("score"),
                            metadata=r.get("metadata", {}),
                        )
                        retrieved_chunks_by_document.setdefault(doc_id, []).append(chunk)
            except Exception as e:
                logger.warning(f"Failed fetching expanded doc {doc_id[:8]}: {e}")

    retrieval_plan_dict = {
        "seed_canonical_ids": sorted(seed_canonical_ids),
        "expanded_canonical_ids": sorted(expanded_canonical_ids),
        "seed_docs": len(seed_doc_ids),
        "expanded_docs": len(missing_doc_ids),
        "total_docs": len(retrieved_chunks_by_document),
    }

    logger.info(f"✅ Hybrid retrieval complete: {retrieval_plan_dict}")
    return retrieved_chunks_by_document, retrieval_plan_dict


# ------------------------------------------------------------------
# MAIN RAG PIPELINE
# ------------------------------------------------------------------

async def run_rag(
    query: str,
    repo_id: Optional[str] = None,
    top_k: int = 20,
    max_chunks_per_doc: int = 5,
    max_total_tokens: int = 4096,
    provider: Optional[str] = None,
    model: Optional[str] = None,
    chunk_filter_fn: Optional[Callable[[RetrievedChunk], bool]] = None,
) -> RAGResult:

    settings = get_settings()
    resolved_repo_id = await resolve_repo_id_http(repo_id)

    embedder = get_embedder(
        provider=settings.EMBEDDING_PROVIDER,
        ollama_base_url=settings.OLLAMA_BASE_URL,
        ollama_model=settings.OLLAMA_EMBED_MODEL,
        ollama_batch_size=settings.OLLAMA_BATCH_SIZE,
    )
    query_embedding = embed_query(query, embedder)

    retrieved_chunks_by_document, retrieval_plan_dict = await hybrid_retrieve(
        query, resolved_repo_id, query_embedding, top_k
    )
    seed_document_ids = list(retrieved_chunks_by_document.keys())

    plan = RetrievalPlan(
        seed_document_ids=set(seed_document_ids),
        expanded_document_ids=set(),
        expansion_metadata={},
        constraints=None,
    )
    retrieved_context = execute_retrieval_plan(
        plan=plan,
        retrieved_chunks_by_document=retrieved_chunks_by_document,
        debug=True,
    )

    agent_chunks_raw = prepare_chunks_for_agent(
        retrieved_context,
        document_order=seed_document_ids,
        max_chunks_per_doc=max_chunks_per_doc,
        max_total_chunks=9999,
        filter_chunk=chunk_filter_fn,
        debug=True,
    )
    agent_chunks = [cast(Dict[str, Any], c) for c in agent_chunks_raw]

    # Token budget
    context_parts: List[str] = []
    token_count = 0
    for c in agent_chunks:
        tokens = len(str(c["text"]).split())
        if token_count + tokens > max_total_tokens:
            break
        context_parts.append(str(c["text"]))
        token_count += tokens
    context_str = "\n\n".join(context_parts)
    logger.info(f"Final context: ~{token_count} tokens from {len(agent_chunks)} chunks")

    # LLM call
    llm_payload = {"context": context_str, "query": query}
    params: Dict[str, str] = {}
    if provider:
        params["provider"] = provider
    if model:
        params["model"] = model

    llm_url = f"{settings.LLM_SERVICE_URL}/generate"
    async with httpx.AsyncClient(timeout=200) as client:
        resp = await client.post(llm_url, json=llm_payload, params=params)
        resp.raise_for_status()
        result = resp.json()

    sources = [c["document_id"] for c in agent_chunks]

    return RAGResult(
        answer=result.get("response", ""),
        sources=sources,
        repo_id=resolved_repo_id,
        retrieval_plan=retrieval_plan_dict,
    )