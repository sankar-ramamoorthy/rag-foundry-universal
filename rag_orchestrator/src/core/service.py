# rag_orchestrator/src/core/service.py
# ADR-045 Hybrid Vector + Graph RAG (HTTP-only, clean boundaries)

import asyncio
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
from rag_orchestrator.src.retrieval.agent_adapter import (
    build_labeled_context,
    build_sources,
    prepare_chunks_for_agent,
)
from rag_orchestrator.src.retrieval.types import RetrievedChunk

from rag_orchestrator.src.retrieval.codebase_utils import (
    extract_canonical_ids_from_chunks,
    dedupe_near_identical_chunks,
)
from rag_orchestrator.src.retrieval.traversal_selector import (
    select_traversal_strategies,
    execute_traversals_from_seeds,
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
    # WP-M5: model actually used by llm_service (incl. WP-M2 fallbacks)
    model_used: Optional[str] = None
    model_alias: Optional[str] = None
    fallback_from: Optional[str] = None


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

async def canonical_to_document_map_http(
    repo_id: str,
    canonical_ids: Set[str],
) -> Dict[str, str]:
    """
    Resolve canonical_ids to a canonical_id → document_id map via the
    ingestion_service graph API. The mapping (not just a set) lets the
    caller apply the expansion ranking when capping fetched docs
    (issue #30 Part 3).
    """
    if not canonical_ids:
        return {}

    settings = get_settings()
    url = f"{settings.INGESTION_SERVICE_URL}/v1/graph/repos/{repo_id}/nodes"
    logger.info(f"url = {url}")
    params = {"canonical_ids": ",".join(sorted(canonical_ids))}

    async with httpx.AsyncClient(timeout=200) as client:
        try:
            resp = await client.get(url, params=params)
            resp.raise_for_status()
            data = resp.json()

            mapping = {
                node["canonical_id"]: node["document_id"]
                for node in data.get("nodes", [])
                if node.get("canonical_id") and node.get("document_id")
            }
            logger.info(
                f"Graph API: {len(canonical_ids)} canonical_ids → "
                f"{len(mapping)} document_ids"
            )
            return mapping

        except Exception as e:
            logger.warning(f"Graph lookup failed: {e}")
            return {}


# ------------------------------------------------------------------
# HYBRID RETRIEVAL (Vector → Canonical → Graph → Docs → Chunks)
# ------------------------------------------------------------------

def _rank_expanded_canonical_ids(
    query: str,
    repo_id: str,
    seed_canonical_ids: Set[str],
) -> List[str]:
    """
    Graph-expand from every seed and return expanded canonical_ids,
    most seed-adjacent first, seeds excluded. The order drives the
    MAX_EXPANDED_DOCS cap (issue #30 Part 3).
    """
    if not seed_canonical_ids:
        return []

    from rag_orchestrator.src.retrieval.codebase_utils import get_cached_graph

    graph: CodebaseGraph = get_cached_graph(repo_id)
    strategies = select_traversal_strategies(query, seed_canonical_ids)
    # F-12: expand from every seed, not just the longest-named one
    expanded_nodes: List[Node] = execute_traversals_from_seeds(
        graph, seed_canonical_ids, strategies
    )
    return [
        node.canonical_id
        for node in expanded_nodes
        if node.canonical_id not in seed_canonical_ids
    ]


async def _fetch_expanded_doc_chunks(
    expanded_doc_ids: List[str],
) -> List[tuple[str, List[Dict[str, Any]]]]:
    """
    Fetch chunks for the capped expanded docs concurrently (bounded by
    MAX_CONCURRENT_DOC_FETCHES), k=EXPANDED_DOC_CHUNKS per doc. Results
    come back in expanded_doc_ids order, so output stays deterministic.
    """
    settings = get_settings()
    doc_url = f"{settings.VECTOR_STORE_URL}/v1/vectors/search-by-doc"
    fetch_semaphore = asyncio.Semaphore(settings.MAX_CONCURRENT_DOC_FETCHES)

    async with httpx.AsyncClient(timeout=200) as client:

        async def fetch_one(doc_id: str) -> tuple[str, List[Dict[str, Any]]]:
            async with fetch_semaphore:
                try:
                    resp = await client.post(
                        doc_url,
                        json={
                            "document_id": doc_id,
                            "k": settings.EXPANDED_DOC_CHUNKS,
                        },
                    )
                    if resp.status_code == 200:
                        return doc_id, resp.json().get("results", [])
                    logger.warning(
                        f"search-by-doc non-200 for {doc_id[:8]}: {resp.status_code}"
                    )
                except Exception as e:
                    logger.warning(f"Failed fetching expanded doc {doc_id[:8]}: {e}")
                return doc_id, []

        return list(
            await asyncio.gather(*(fetch_one(doc_id) for doc_id in expanded_doc_ids))
        )


def _add_chunks(
    doc_id: str,
    results: List[Dict[str, Any]],
    seen_chunk_ids: Set[str],
    retrieved_chunks_by_document: Dict[str, List[RetrievedChunk]],
) -> List[RetrievedChunk]:
    """Append result rows as RetrievedChunks, skipping seen chunk_ids."""
    added: List[RetrievedChunk] = []
    for r in results:
        if r["chunk_id"] in seen_chunk_ids:
            continue
        seen_chunk_ids.add(r["chunk_id"])
        chunk = RetrievedChunk(
            document_id=doc_id,
            chunk_id=r["chunk_id"],
            text=r["text"],
            score=r.get("score"),
            metadata=r.get("metadata", {}),
        )
        added.append(chunk)
        retrieved_chunks_by_document.setdefault(doc_id, []).append(chunk)
    return added


async def hybrid_retrieve(
    query: str,
    repo_id: str,
    query_embedding: List[float],
    top_k: int = 20,
    language: Optional[str] = None,
) -> tuple[Dict[str, List[RetrievedChunk]], Dict[str, Any]]:
    """
    Implements ADR-045 hybrid retrieval pipeline.

    `language` (WP-L6a, #85) optionally scopes the seed search to one
    language (python/typescript/javascript); omitted, retrieval is
    unfiltered by language exactly as before this feature existed. The
    scope survives the source_type-relaxation fallback below the same way
    repo_id already does (issue #30 Part 1) — graph-traversal expansion
    needs no separate language filter, since it only ever expands from an
    already-scoped seed set.

    Returns:
        retrieved_chunks_by_document,
        retrieval_plan_dict
    """
    settings = get_settings()
    logger.info(f"🔄 Hybrid retrieval | repo={repo_id[:8]} | q='{query[:50]}...'")

    search_url = f"{settings.VECTOR_STORE_URL}/v1/vectors/search"
    seed_filter: Dict[str, Any] = {"source_type": "code", "repo_id": repo_id}
    if language:
        seed_filter["language"] = language
    payload = {"query_vector": query_embedding, "k": top_k,
                "metadata_filter": seed_filter}

    async with httpx.AsyncClient(timeout=200) as client:
        resp = await client.post(search_url, json=payload)
        if resp.status_code != 200 or not resp.json().get("results"):
            logger.info("No code chunks found. Falling back to repo-scoped search.")
            # Relax only source_type — the fallback must never leave the
            # repo or the requested language, or queries against a
            # sparsely-populated scope silently answer from outside it
            # (issue #30 Part 1; WP-L6a extends the same reasoning to
            # language).
            fallback_filter: Dict[str, Any] = {"repo_id": repo_id}
            if language:
                fallback_filter["language"] = language
            payload["metadata_filter"] = fallback_filter
            resp = await client.post(search_url, json=payload)
        resp.raise_for_status()
        raw_results = resp.json().get("results", [])

    retrieved_chunks_by_document: Dict[str, List[RetrievedChunk]] = {}
    seen_chunk_ids: Set[str] = set()
    seed_chunks: List[RetrievedChunk] = []
    for r in raw_results:
        doc_id = r.get("document_id") or r.get("metadata", {}).get("document_id")
        if not doc_id:
            continue
        seed_chunks.extend(
            _add_chunks(doc_id, [r], seen_chunk_ids, retrieved_chunks_by_document)
        )

    # Issue #65: drop near-duplicate seed chunks (a module/root artifact
    # whose sole child covers ~the same text) before they consume top-k
    # candidate slots. Only seed chunks are populated in
    # retrieved_chunks_by_document at this point — expansion below adds
    # more, untouched by this filter.
    seed_chunks = dedupe_near_identical_chunks(seed_chunks)
    kept_chunk_ids = {c.chunk_id for c in seed_chunks}
    retrieved_chunks_by_document = {
        doc_id: kept
        for doc_id, doc_chunks in retrieved_chunks_by_document.items()
        if (kept := [c for c in doc_chunks if c.chunk_id in kept_chunk_ids])
    }

    seed_canonical_ids = extract_canonical_ids_from_chunks(seed_chunks)
    logger.info(
        f"📊 {len(seed_chunks)} chunks → {len(seed_canonical_ids)} canonical_ids"
    )

    expanded_ranked = _rank_expanded_canonical_ids(query, repo_id, seed_canonical_ids)
    expanded_canonical_ids = set(expanded_ranked)

    all_canonical_ids = seed_canonical_ids | expanded_canonical_ids
    canonical_to_doc = await canonical_to_document_map_http(repo_id, all_canonical_ids)

    seed_doc_ids = set(retrieved_chunks_by_document.keys())

    # Issue #30 Part 3: cap expansion breadth. Rank order is preserved
    # from execute_traversals_from_seeds; docs beyond MAX_EXPANDED_DOCS
    # are counted as considered but never fetched.
    expanded_doc_ids: List[str] = []
    expanded_doc_seen: Set[str] = set(seed_doc_ids)
    for cid in expanded_ranked:
        doc_id = canonical_to_doc.get(cid)
        if not doc_id or doc_id in expanded_doc_seen:
            continue
        expanded_doc_seen.add(doc_id)
        expanded_doc_ids.append(doc_id)

    expanded_docs_considered = len(expanded_doc_ids)
    expanded_doc_ids = expanded_doc_ids[: settings.MAX_EXPANDED_DOCS]

    fetched = await _fetch_expanded_doc_chunks(expanded_doc_ids)
    for doc_id, doc_results in fetched:
        _add_chunks(doc_id, doc_results, seen_chunk_ids, retrieved_chunks_by_document)

    retrieval_plan_dict = {
        "seed_canonical_ids": sorted(seed_canonical_ids),
        "expanded_canonical_ids": sorted(expanded_canonical_ids),
        "seed_docs": len(seed_doc_ids),
        "expanded_docs_considered": expanded_docs_considered,
        "expanded_docs_used": len(expanded_doc_ids),
        "expanded_docs": len(expanded_doc_ids),
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
    language: Optional[str] = None,
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
        query, resolved_repo_id, query_embedding, top_k, language=language
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
        # Issue #30 Part 3: real cap (was 9999). document_order lists
        # seed docs before expanded ones, so truncation drops expansion
        # first.
        max_total_chunks=settings.MAX_TOTAL_CHUNKS,
        filter_chunk=chunk_filter_fn,
        debug=True,
    )
    agent_chunks = [cast(Dict[str, Any], c) for c in agent_chunks_raw]

    # Token budget
    context_str, token_count = build_labeled_context(agent_chunks, max_total_tokens)
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

    # Issue #30 Part 4: canonical IDs / paths, deduplicated, seeds first
    sources = build_sources(agent_chunks)

    return RAGResult(
        answer=result.get("response", ""),
        sources=sources,
        repo_id=resolved_repo_id,
        retrieval_plan=retrieval_plan_dict,
        model_used=result.get("model"),
        model_alias=result.get("model_alias"),
        fallback_from=result.get("fallback_from"),
    )
