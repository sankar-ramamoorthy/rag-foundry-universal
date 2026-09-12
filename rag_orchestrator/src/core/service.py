# rag_orchestrator/src/core/service.py
# ADR-045 Hybrid Vector + Graph RAG (HTTP-only, clean boundaries)

import asyncio
import logging
import uuid
from dataclasses import dataclass
from typing import List, Optional, Callable, Dict, Any, Set, cast
import httpx

from fastapi import HTTPException
from pydantic import BaseModel

from src.core.config import get_settings
from shared.embedders.query import embed_query
from shared.embedders.factory import get_embedder

from shared.retrieval.retrieval_plan import (
    ExpansionMetadata,
    RetrievalConstraints,
    RetrievalPlan,
)
from rag_orchestrator.src.retrieval.execute_plan import execute_retrieval_plan
from rag_orchestrator.src.retrieval.agent_adapter import (
    build_labeled_context,
    build_sources,
    prepare_chunks_for_agent,
    select_chunks_within_token_budget,
)
from rag_orchestrator.src.retrieval.types import RetrievedChunk

from rag_orchestrator.src.retrieval.codebase_utils import (
    canonical_id_from_metadata,
    extract_canonical_ids_from_chunks,
    dedupe_near_identical_chunks,
)
from rag_orchestrator.src.retrieval.evidence_trace import (
    compute_partial_evidence_survival,
    finalize_evidence_survival,
)
from rag_orchestrator.src.retrieval.traversal_selector import (
    select_traversal_strategies,
    execute_traversals_from_seeds_detailed,
)
from rag_orchestrator.src.retrieval.codebase_queries import CodebaseGraph

logger = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO)


def _new_trace_id() -> str:
    """WP-T1b: one trace_id per /v1/rag request."""
    return uuid.uuid4().hex


def _log_stage(trace_id: str, stage: str, **fields: Any) -> None:
    """
    WP-T1b: one structured-ish log line per retrieval-pipeline checkpoint,
    all carrying the same trace_id so a single request's stages can be
    correlated (by grepping for the trace_id) without reconstructing the
    call by hand from unrelated log lines. Deliberately plain `logging`,
    not a new structured-logging/tracing framework -- see WP-T1's scope
    note in DOCS/audit/WP-T1-retrieval-evidence-trace.md (that belongs to
    Phase 4's WP-E5, sequenced after this).
    """
    rendered = " ".join(f"{key}={value}" for key, value in fields.items())
    logger.info(f"trace_id={trace_id} stage={stage} {rendered}".rstrip())


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
    # WP-T1b: one ID connecting every stage-event log line for this
    # request, for evidence-survival tracing.
    trace_id: Optional[str] = None


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

@dataclass(frozen=True)
class ExpansionRanking:
    """
    WP-T1a: `_rank_expanded_canonical_ids`'s result, extended with the
    relation type and originating seed for each expanded canonical_id
    (previously computed by traversal_selector and then discarded) so
    `hybrid_retrieve` can populate RetrievalPlan.expansion_metadata
    instead of leaving it always empty.
    """
    expanded_ranked: List[str]
    relation_type_by_canonical_id: Dict[str, str]
    source_seed_by_canonical_id: Dict[str, str]


def _rank_expanded_canonical_ids(
    query: str,
    repo_id: str,
    seed_canonical_ids: Set[str],
) -> ExpansionRanking:
    """
    Graph-expand from every seed and return expanded canonical_ids,
    most seed-adjacent first, seeds excluded. The order drives the
    MAX_EXPANDED_DOCS cap (issue #30 Part 3).
    """
    if not seed_canonical_ids:
        return ExpansionRanking([], {}, {})

    from rag_orchestrator.src.retrieval.codebase_utils import get_cached_graph

    graph: CodebaseGraph = get_cached_graph(repo_id)
    strategies = select_traversal_strategies(query, seed_canonical_ids)
    # F-12: expand from every seed, not just the longest-named one
    candidates = execute_traversals_from_seeds_detailed(
        graph, seed_canonical_ids, strategies
    )
    expanded_ranked: List[str] = []
    relation_type_by_cid: Dict[str, str] = {}
    source_seed_by_cid: Dict[str, str] = {}
    for candidate in candidates:
        cid = candidate.node.canonical_id
        if cid in seed_canonical_ids:
            continue
        expanded_ranked.append(cid)
        relation_type_by_cid[cid] = candidate.relation_type
        source_seed_by_cid[cid] = candidate.source_seed_canonical_id
    return ExpansionRanking(expanded_ranked, relation_type_by_cid, source_seed_by_cid)


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
    for index, r in enumerate(results):
        if r["chunk_id"] in seen_chunk_ids:
            continue
        seen_chunk_ids.add(r["chunk_id"])
        metadata = r.get("metadata", {})
        chunk = RetrievedChunk(
            document_id=doc_id,
            chunk_id=r["chunk_id"],
            text=r["text"],
            score=r.get("score"),
            metadata=metadata,
            canonical_id=canonical_id_from_metadata(metadata) or None,
            # WP-T1c: position within this results list -- the ordered
            # /search-by-doc response for expanded docs, or a
            # single-item list per seed chunk.
            chunk_index=index,
        )
        added.append(chunk)
        retrieved_chunks_by_document.setdefault(doc_id, []).append(chunk)
    return added


def _build_expansion_metadata(
    *,
    expanded_ranked: List[str],
    expanded_doc_ids: List[str],
    ranking: "ExpansionRanking",
    canonical_to_doc: Dict[str, str],
    retrieved_chunks_by_document: Dict[str, List[RetrievedChunk]],
) -> Dict[str, ExpansionMetadata]:
    """
    WP-T1a: populate RetrievalPlan.expansion_metadata (previously always
    {} on this path) with the relation type and source seed for every
    expanded document that actually survived the cap and had chunks
    fetched -- restricted to expanded_doc_ids (the post-cap list) so this
    exactly matches the set of documents run_rag treats as "expanded"
    elsewhere, with no behavior change to what gets fetched or ranked.
    """
    expansion_metadata: Dict[str, ExpansionMetadata] = {}
    expanded_doc_ids_with_chunks = set(expanded_doc_ids) & set(
        retrieved_chunks_by_document.keys()
    )
    for cid in expanded_ranked:
        doc_id = canonical_to_doc.get(cid)
        if (
            not doc_id
            or doc_id not in expanded_doc_ids_with_chunks
            or doc_id in expansion_metadata
        ):
            continue
        source_seed_cid = ranking.source_seed_by_canonical_id.get(cid)
        source_doc_id = (
            canonical_to_doc.get(source_seed_cid) if source_seed_cid else None
        )
        if not source_doc_id:
            continue
        expansion_metadata[doc_id] = ExpansionMetadata(
            source_document_id=source_doc_id,
            relation_type=ranking.relation_type_by_canonical_id.get(cid, "UNKNOWN"),
        )
    return expansion_metadata


async def hybrid_retrieve(
    query: str,
    repo_id: str,
    query_embedding: List[float],
    top_k: int = 20,
    language: Optional[str] = None,
    trace_canonical_ids: Optional[Set[str]] = None,
    trace_id: Optional[str] = None,
) -> tuple[Dict[str, List[RetrievedChunk]], Dict[str, Any]]:
    """
    Implements ADR-045 hybrid retrieval pipeline.

    `trace_id` (WP-T1b) identifies this request across every stage-event
    log line hybrid_retrieve emits; generated if omitted, so callers that
    invoke hybrid_retrieve directly (e.g. tests, notebooks) still get one.

    `trace_canonical_ids` (issue #89) is an optional evaluation/debug hook:
    when given, the returned retrieval_plan_dict carries a
    "_evidence_trace_partial" entry recording, for each of those canonical
    IDs, whether it was found by vector search, found by graph expansion (and
    at what rank), survived the MAX_EXPANDED_DOCS cap, and had a chunk
    fetched. It costs nothing when omitted (the default, used by every
    production call) and does not affect retrieval behavior either way.

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
    trace_id = trace_id or _new_trace_id()
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
    _log_stage(
        trace_id,
        "retrieval.seed.completed",
        seed_chunks=len(seed_chunks),
        seed_canonical_ids=len(seed_canonical_ids),
        seed_docs=len(retrieved_chunks_by_document),
    )

    ranking = _rank_expanded_canonical_ids(query, repo_id, seed_canonical_ids)
    expanded_ranked = ranking.expanded_ranked
    expanded_canonical_ids = set(expanded_ranked)
    _log_stage(
        trace_id,
        "graph.expand.completed",
        expanded_canonical_ids=len(expanded_canonical_ids),
    )

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
    _log_stage(
        trace_id,
        "expansion.cap.applied",
        expanded_docs_considered=expanded_docs_considered,
        expanded_docs_used=len(expanded_doc_ids),
    )

    fetched = await _fetch_expanded_doc_chunks(expanded_doc_ids)
    # WP-T1c: chunk indices requested (always range(EXPANDED_DOC_CHUNKS),
    # the k passed to /search-by-doc) vs. actually returned (post
    # cross-document chunk_id dedup, so a chunk already seen as a seed or
    # via another expanded doc is excluded here even if the store
    # returned it).
    chunks_requested_by_document: Dict[str, List[int]] = {
        doc_id: list(range(settings.EXPANDED_DOC_CHUNKS)) for doc_id in expanded_doc_ids
    }
    chunks_returned_by_document: Dict[str, List[int]] = {}
    for doc_id, doc_results in fetched:
        added = _add_chunks(
            doc_id, doc_results, seen_chunk_ids, retrieved_chunks_by_document
        )
        chunks_returned_by_document[doc_id] = [
            c.chunk_index for c in added if c.chunk_index is not None
        ]
    _log_stage(
        trace_id,
        "chunks.fetch.completed",
        docs_fetched=len(expanded_doc_ids),
        docs_with_chunks=sum(1 for _, results in fetched if results),
        total_docs=len(retrieved_chunks_by_document),
    )

    expansion_metadata = _build_expansion_metadata(
        expanded_ranked=expanded_ranked,
        expanded_doc_ids=expanded_doc_ids,
        ranking=ranking,
        canonical_to_doc=canonical_to_doc,
        retrieved_chunks_by_document=retrieved_chunks_by_document,
    )

    retrieval_plan_dict = {
        # WP-T1b: one ID connecting every stage-event log line above for
        # this request.
        "trace_id": trace_id,
        "seed_canonical_ids": sorted(seed_canonical_ids),
        "expanded_canonical_ids": sorted(expanded_canonical_ids),
        "seed_docs": len(seed_doc_ids),
        "expanded_docs_considered": expanded_docs_considered,
        "expanded_docs_used": len(expanded_doc_ids),
        "expanded_docs": len(expanded_doc_ids),
        "total_docs": len(retrieved_chunks_by_document),
        # WP-T1a: raw pieces run_rag needs to build a properly split
        # RetrievalPlan (seed_document_ids/expanded_document_ids used to
        # both be collapsed into one set with expansion_metadata always
        # empty). Kept in the dict (not popped) so they're also visible
        # in RAGResult.retrieval_plan for inspection.
        "seed_document_ids": sorted(seed_doc_ids),
        "expanded_document_ids": sorted(expansion_metadata.keys()),
        "expansion_metadata": {
            doc_id: {
                "source_document_id": meta.source_document_id,
                "relation_type": meta.relation_type,
            }
            for doc_id, meta in expansion_metadata.items()
        },
        # WP-T1c: chunk-index-level detail on /search-by-doc fetches.
        "chunks_requested_by_document": chunks_requested_by_document,
        "chunks_returned_by_document": chunks_returned_by_document,
    }

    if trace_canonical_ids:
        fetched_doc_ids_with_chunks = {
            doc_id for doc_id, results in fetched if results
        }
        retrieval_plan_dict["_evidence_trace_partial"] = (
            compute_partial_evidence_survival(
                target_canonical_ids=trace_canonical_ids,
                seed_canonical_ids=seed_canonical_ids,
                expanded_ranked=expanded_ranked,
                canonical_to_doc=canonical_to_doc,
                expanded_doc_ids_used=expanded_doc_ids,
                fetched_doc_ids_with_chunks=fetched_doc_ids_with_chunks,
            )
        )

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
    trace_canonical_ids: Optional[Set[str]] = None,
) -> RAGResult:

    settings = get_settings()
    trace_id = _new_trace_id()
    _log_stage(trace_id, "rag.query.started", repo_id=repo_id, top_k=top_k)

    resolved_repo_id = await resolve_repo_id_http(repo_id)

    embedder = get_embedder(
        provider=settings.EMBEDDING_PROVIDER,
        ollama_base_url=settings.OLLAMA_BASE_URL,
        ollama_model=settings.OLLAMA_EMBED_MODEL,
        ollama_batch_size=settings.OLLAMA_BATCH_SIZE,
    )
    query_embedding = embed_query(query, embedder)

    retrieved_chunks_by_document, retrieval_plan_dict = await hybrid_retrieve(
        query,
        resolved_repo_id,
        query_embedding,
        top_k,
        language=language,
        trace_canonical_ids=trace_canonical_ids,
        trace_id=trace_id,
    )
    # NOTE: seed_document_ids here means "every document with retrieved
    # chunks, seed and expanded merged" -- prepare_chunks_for_agent below
    # relies on this dict's insertion order (seeds added before expanded
    # docs) to drop expansion first on truncation. It is NOT the same as
    # the true seed-only set used to build `plan` below (WP-T1a).
    seed_document_ids = list(retrieved_chunks_by_document.keys())

    # WP-T1a: build the RetrievalPlan from the actual seed/expanded split
    # and per-document expansion metadata hybrid_retrieve computed, instead
    # of collapsing everything into seed_document_ids with an always-empty
    # expansion_metadata.
    true_seed_document_ids = set(retrieval_plan_dict["seed_document_ids"])
    expanded_document_ids = set(retrieval_plan_dict["expanded_document_ids"])
    expansion_metadata = {
        doc_id: ExpansionMetadata(**meta)
        for doc_id, meta in retrieval_plan_dict["expansion_metadata"].items()
    }

    plan = RetrievalPlan(
        seed_document_ids=true_seed_document_ids,
        expanded_document_ids=expanded_document_ids,
        expansion_metadata=expansion_metadata,
        constraints=RetrievalConstraints(),
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

    # WP-T1c: two genuinely distinct survival stages, both computed before
    # the LLM call so the evidence trace and retrieval_plan can report
    # each separately instead of conflating them.
    #   1. survives_chunk_limits: made it past execute_retrieval_plan's
    #      per-document slice and prepare_chunks_for_agent's chunk-count
    #      limits -- this is `agent_chunks` as-is.
    #   2. reaches_final_context: of those, which also survive
    #      build_labeled_context's token-budget truncation.
    chunk_limited_document_ids = {
        cast(str, c["document_id"]) for c in agent_chunks
    }
    _log_stage(
        trace_id,
        "chunks.limit.applied",
        agent_chunks=len(agent_chunks),
        documents=len(chunk_limited_document_ids),
    )
    tokens_before_budget = sum(len(str(c["text"]).split()) for c in agent_chunks)
    chunks_in_final_context = select_chunks_within_token_budget(
        agent_chunks, max_total_tokens
    )
    final_context_document_ids = {
        cast(str, c["document_id"]) for c in chunks_in_final_context
    }
    _log_stage(
        trace_id,
        "context.token_budget.applied",
        tokens_before_budget=tokens_before_budget,
        chunks_in_final_context=len(chunks_in_final_context),
        documents=len(final_context_document_ids),
    )

    evidence_trace_partial = retrieval_plan_dict.pop("_evidence_trace_partial", None)
    if evidence_trace_partial is not None:
        retrieval_plan_dict["evidence_trace"] = finalize_evidence_survival(
            evidence_trace_partial,
            chunk_limited_document_ids,
            final_context_document_ids,
        )

    # Token budget
    context_str, token_count = build_labeled_context(agent_chunks, max_total_tokens)
    retrieval_plan_dict["tokens_before_budget"] = tokens_before_budget
    retrieval_plan_dict["tokens_after_budget"] = token_count
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
    _log_stage(
        trace_id,
        "llm.generate.completed",
        model=result.get("model"),
        fallback_from=result.get("fallback_from"),
    )

    # Issue #30 Part 4: canonical IDs / paths, deduplicated, seeds first
    sources = build_sources(agent_chunks)

    _log_stage(
        trace_id,
        "rag.query.completed",
        sources=len(sources),
        answer_chars=len(result.get("response", "")),
    )

    return RAGResult(
        answer=result.get("response", ""),
        sources=sources,
        repo_id=resolved_repo_id,
        retrieval_plan=retrieval_plan_dict,
        model_used=result.get("model"),
        model_alias=result.get("model_alias"),
        fallback_from=result.get("fallback_from"),
        trace_id=trace_id,
    )
