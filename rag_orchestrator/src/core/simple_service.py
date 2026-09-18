# rag_orchestrator/src/core/simple_service.py
"""
Simple RAG pipeline with document graph expansion (ADR-046).
For uploaded documents: PDFs, text files, Markdown.

Flow:
    embed query
    → vector search (excludes code chunks)
    → expand RetrievalPlan via DEFINES relationships (MS6-IS3)
    → fetch chunks for expanded docs
    → token budget
    → LLM
"""
import asyncio
import logging
from typing import List, Optional, Callable, Dict, Any, cast

import httpx
import requests as req_lib
from fastapi import HTTPException
from pydantic import BaseModel

from src.core.config import get_settings
from shared.embedders.query import embed_query
from shared.embedders.factory import get_embedder
from shared.retrieval.retrieval_plan import RetrievalPlan
from rag_orchestrator.src.retrieval.execute_plan import execute_retrieval_plan
from rag_orchestrator.src.retrieval.agent_adapter import (
    assemble_context,
    build_final_context_manifest,
    conservative_token_count,
    build_sources,
    prepare_chunks_for_agent,
)
from rag_orchestrator.src.retrieval.types import RetrievedChunk
from rag_orchestrator.src.retrieval.traversal_planner import (
    expand_retrieval_plan,
    TraversalConstraints,
)
from src.core.reranker import rerank_chunks
from rag_orchestrator.src.retrieval.codebase_utils import canonical_id_from_metadata

logger = logging.getLogger(__name__)


class SimpleRAGResult(BaseModel):
    answer: str
    sources: List[str]
    final_context_manifest: List[Dict[str, Any]] = []
    # WP-M5: model actually used by llm_service (incl. WP-M2 fallbacks)
    model_used: Optional[str] = None
    model_alias: Optional[str] = None
    fallback_from: Optional[str] = None
    # WP-S8: whether the optional cross-encoder reranker ran (see
    # core/service.py's RAGResult.reranked for the full rationale --
    # this is the non-graph document-RAG path's counterpart).
    reranked: bool = False


async def run_simple_rag(  # noqa: C901 - decompose with WP-S8 retrieval work
    query: str,
    top_k: int = 20,
    max_chunks_per_doc: int = 5,
    max_total_tokens: int = 2048,
    provider: str | None = None,
    model: str | None = None,
    chunk_filter_fn: Optional[Callable[[RetrievedChunk], bool]] = None,
    rerank: Optional[bool] = None,
) -> SimpleRAGResult:

    settings = get_settings()

    # ------------------------------------------------------------------
    # Step 1: Embed query
    # ------------------------------------------------------------------
    embedder = get_embedder(
        provider=settings.EMBEDDING_PROVIDER,
        ollama_base_url=settings.OLLAMA_BASE_URL,
        ollama_model=settings.OLLAMA_EMBED_MODEL,
        ollama_batch_size=settings.OLLAMA_BATCH_SIZE,
    )
    # #170 (WP-R7): embed_query -> OllamaEmbedder.embed makes a synchronous
    # requests.post; off the event loop.
    query_embedding = await asyncio.to_thread(embed_query, query, embedder)

    # ------------------------------------------------------------------
    # Step 2: Vector search — exclude code chunks
    # ------------------------------------------------------------------
    search_url = f"{settings.VECTOR_STORE_URL}/v1/vectors/search"
    payload = {
        "query_vector": query_embedding,
        "k": top_k,
        "metadata_filter": {"source_type": {"ne": "code"}},
    }

    async with httpx.AsyncClient(timeout=120) as client:
        try:
            resp = await client.post(search_url, json=payload)
            resp.raise_for_status()
            raw_results = resp.json().get("results", [])
        except Exception as e:
            logger.error("Vector search failed: %s", e)
            raise HTTPException(status_code=500, detail=str(e))

    logger.info("Simple RAG: vector search returned %d results", len(raw_results))

    # ------------------------------------------------------------------
    # Step 3: Build seed chunks and document map
    # ------------------------------------------------------------------
    seed_document_ids: List[str] = []
    seen: set = set()
    retrieved_chunks_by_document: Dict[str, List[RetrievedChunk]] = {}

    for r in raw_results:
        doc_id = r.get("document_id") or r.get("metadata", {}).get("document_id")
        if not doc_id:
            continue
        if doc_id not in seen:
            seen.add(doc_id)
            seed_document_ids.append(doc_id)
        chunk = RetrievedChunk(
            document_id=doc_id,
            chunk_id=r["chunk_id"],
            text=r["text"],
            score=r.get("score"),
            metadata=r.get("metadata", {}),
            chunk_index=r.get("metadata", {}).get("chunk_index"),
            canonical_id=canonical_id_from_metadata(r.get("metadata", {})) or None,
        )
        retrieved_chunks_by_document.setdefault(doc_id, []).append(chunk)

    logger.info("Simple RAG: %d seed documents", len(seed_document_ids))

    # ------------------------------------------------------------------
    # Step 4: Build initial RetrievalPlan
    # ------------------------------------------------------------------
    plan = RetrievalPlan(
        seed_document_ids=set(seed_document_ids),
        expanded_document_ids=set(),
        expansion_metadata={},
    )

    # ------------------------------------------------------------------
    # Step 5: MS6-IS3 — expand plan via document DEFINES relationships
    # ------------------------------------------------------------------
    def _list_outgoing(document_id: str) -> List[Dict]:
        """
        Fetch outgoing DEFINES relationships from ingestion_service.
        Returns list of dicts with target_document_id and relation_type.
        """
        try:
            url = (
                f"{settings.INGESTION_SERVICE_URL}"
                f"/v1/graph/docs/{document_id}/relationships"
            )
            r = req_lib.get(url, timeout=10)
            if r.status_code == 200:
                return r.json().get("relationships", [])
            logger.warning(
                "Relationships fetch non-200: doc=%s status=%s",
                document_id[:8], r.status_code
            )
        except Exception as e:
            logger.warning("Relationships fetch error for %s: %s", document_id[:8], e)
        return []

    plan = await asyncio.to_thread(
        expand_retrieval_plan,
        plan=plan,
        list_outgoing_relationships=_list_outgoing,
        constraints=TraversalConstraints(
            max_depth=1,
            allowed_relation_types={"DEFINES"},
        ),
    )

    logger.info(
        "Simple RAG after expansion: %d seed + %d expanded docs",
        len(plan.seed_document_ids),
        len(plan.expanded_document_ids),
    )

    # ------------------------------------------------------------------
    # Step 6: Fetch chunks for expanded docs not already retrieved
    # ------------------------------------------------------------------
    from src.core.service import _add_chunks, _fetch_expanded_doc_chunks

    selected_expanded = sorted(plan.expanded_document_ids)[:settings.MAX_EXPANDED_DOCS]
    passage_doc_ids = seed_document_ids + selected_expanded
    fetched = await _fetch_expanded_doc_chunks(
        passage_doc_ids, query_embedding=query_embedding,
    )
    seen_chunk_ids = {c.chunk_id for chunks in retrieved_chunks_by_document.values()
                      for c in chunks}
    for doc_id, results in fetched:
        _add_chunks(doc_id, results, seen_chunk_ids, retrieved_chunks_by_document)
    for chunks in retrieved_chunks_by_document.values():
        chunks.sort(key=lambda c: (-(c.score or 0.0), c.chunk_id))

    # ------------------------------------------------------------------
    # Step 7: Execute RetrievalPlan
    # ------------------------------------------------------------------
    retrieved_context = execute_retrieval_plan(
        plan=plan,
        retrieved_chunks_by_document=retrieved_chunks_by_document,
        top_k_per_document=max_chunks_per_doc,
        debug=True,
    )

    # ------------------------------------------------------------------
    # Step 8: Prepare chunks for agent
    # ------------------------------------------------------------------
    agent_chunks_raw = prepare_chunks_for_agent(
        retrieved_context,
        document_order=passage_doc_ids,
        max_chunks_per_doc=max_chunks_per_doc,
        max_total_chunks=settings.MAX_TOTAL_CHUNKS,
        filter_chunk=chunk_filter_fn,
        debug=True,
    )
    agent_chunks = [cast(Dict[str, Any], c) for c in agent_chunks_raw]

    # ------------------------------------------------------------------
    # Step 8.5: optional cross-encoder reranker (WP-S8), off by default.
    # See core/service.py's equivalent step for the full rationale --
    # this is the non-graph path this feature is expected to matter most
    # for, since there's no graph-expansion signal to fall back on here.
    # ------------------------------------------------------------------
    rerank_active = settings.RERANK_ENABLED if rerank is None else rerank
    if rerank_active:
        # #170 (WP-R7): CrossEncoder.predict is synchronous CPU/GPU work;
        # off the event loop.
        agent_chunks = await asyncio.to_thread(
            rerank_chunks,
            query,
            agent_chunks,
            top_k=settings.RERANK_TOP_K,
            model_name=settings.RERANK_MODEL,
        )
        logger.info("Simple RAG: reranked to %d chunks", len(agent_chunks))

    # ------------------------------------------------------------------
    # Step 9: Token budget enforcement
    # ------------------------------------------------------------------
    context_budget = min(max_total_tokens, max(0, settings.CONTEXT_WINDOW_TOKENS
        - settings.PROMPT_RESERVE_TOKENS - settings.OUTPUT_RESERVE_TOKENS
        - conservative_token_count(query)))
    assembled = assemble_context(agent_chunks, context_budget)
    context_str, token_count = assembled.text, assembled.token_count
    logger.info("Simple RAG: final context ~%d tokens", token_count)

    # ------------------------------------------------------------------
    # Step 10: LLM call
    # ------------------------------------------------------------------
    llm_payload = {"context": context_str, "query": query}
    params: Dict[str, str] = {}
    if provider:
        params["provider"] = provider
    if model:
        params["model"] = model

    async with httpx.AsyncClient(timeout=120) as client:
        try:
            resp = await client.post(
                f"{settings.LLM_SERVICE_URL}/generate",
                json=llm_payload,
                params=params,
            )
            resp.raise_for_status()
            result = resp.json()
        except Exception as e:
            logger.error("LLM call failed: %s", e)
            raise HTTPException(status_code=500, detail=str(e))

    return SimpleRAGResult(
        answer=result.get("response", ""),
        # Issue #30 Part 4: uploaded-file chunks also carry canonical_id/
        # relative_path metadata (pipeline.py), so labels beat raw UUIDs
        sources=build_sources(assembled.chunks),
        final_context_manifest=build_final_context_manifest(
            assembled.chunks, seed_document_ids=set(seed_document_ids),
            expansion_metadata={doc: {
                "relation_type": meta.relation_type,
                "source_document_id": meta.source_document_id,
            } for doc, meta in plan.expansion_metadata.items()},
        ),
        model_used=result.get("model"),
        model_alias=result.get("model_alias"),
        fallback_from=result.get("fallback_from"),
        reranked=rerank_active,
    )
