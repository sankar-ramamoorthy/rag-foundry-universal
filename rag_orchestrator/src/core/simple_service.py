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
from rag_orchestrator.src.retrieval.agent_adapter import prepare_chunks_for_agent
from rag_orchestrator.src.retrieval.types import RetrievedChunk
from rag_orchestrator.src.retrieval.traversal_planner import (
    expand_retrieval_plan,
    TraversalConstraints,
)

logger = logging.getLogger(__name__)


class SimpleRAGResult(BaseModel):
    answer: str
    sources: List[str]


async def run_simple_rag(
    query: str,
    top_k: int = 20,
    max_chunks_per_doc: int = 5,
    max_total_tokens: int = 2048,
    provider: str | None = None,
    model: str | None = None,
    chunk_filter_fn: Optional[Callable[[RetrievedChunk], bool]] = None,
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
    query_embedding = embed_query(query, embedder)

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

    plan = expand_retrieval_plan(
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
    if plan.expanded_document_ids:
        missing_doc_ids = [
            doc_id for doc_id in plan.expanded_document_ids
            if doc_id not in retrieved_chunks_by_document
        ]

        if missing_doc_ids:
            search_by_doc_url = (
                f"{settings.VECTOR_STORE_URL}/v1/vectors/search-by-doc"
            )
            async with httpx.AsyncClient(timeout=60) as client:
                for doc_id in missing_doc_ids:
                    try:
                        resp = await client.post(
                            search_by_doc_url,
                            json={"document_id": doc_id, "k": 3},
                        )
                        if resp.status_code == 200:
                            for result in resp.json().get("results", []):
                                chunk = RetrievedChunk(
                                    document_id=doc_id,
                                    chunk_id=result["chunk_id"],
                                    text=result["text"],
                                    score=result.get("score"),
                                    metadata=result.get("metadata", {}),
                                )
                                retrieved_chunks_by_document.setdefault(
                                    doc_id, []
                                ).append(chunk)
                        else:
                            logger.warning(
                                "search-by-doc failed: doc=%s status=%s",
                                doc_id[:8], resp.status_code
                            )
                    except Exception as e:
                        logger.warning(
                            "search-by-doc error for %s: %s", doc_id[:8], e
                        )

            logger.info(
                "Simple RAG: fetched chunks for %d expanded docs",
                len(missing_doc_ids)
            )

    # ------------------------------------------------------------------
    # Step 7: Execute RetrievalPlan
    # ------------------------------------------------------------------
    retrieved_context = execute_retrieval_plan(
        plan=plan,
        retrieved_chunks_by_document=retrieved_chunks_by_document,
        debug=True,
    )

    # ------------------------------------------------------------------
    # Step 8: Prepare chunks for agent
    # ------------------------------------------------------------------
    agent_chunks_raw = prepare_chunks_for_agent(
        retrieved_context,
        document_order=seed_document_ids,
        max_chunks_per_doc=max_chunks_per_doc,
        max_total_chunks=9999,
        filter_chunk=chunk_filter_fn,
        debug=True,
    )
    agent_chunks = [cast(Dict[str, Any], c) for c in agent_chunks_raw]

    # ------------------------------------------------------------------
    # Step 9: Token budget enforcement
    # ------------------------------------------------------------------
    context_parts: List[str] = []
    token_count = 0
    for c in agent_chunks:
        tokens = len(str(c["text"]).split())
        if token_count + tokens > max_total_tokens:
            break
        context_parts.append(str(c["text"]))
        token_count += tokens

    context_str = "\n\n".join(context_parts)
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
        sources=list(dict.fromkeys(c["document_id"] for c in agent_chunks)),
        # dict.fromkeys preserves order and deduplicates
    )