# rag_orchestrator/src/retrieval/evidence_trace.py
"""
Issue #89: minimal instrumentation to observe whether specific pieces of
graph-discovered evidence survive each stage of hybrid retrieval, instead of
reconstructing that survival by hand from logs and DB queries (see
DOCS/test_results/2026-09-03-rag-retrieval-quality-linux-tailscale-baseline.md
section 13 for the manual version of this diagnosis).

Stages tracked, matching the pipeline in service.py#hybrid_retrieve and
service.py#run_rag:

  found_by_vector        -> present in the vector-search seed set
  found_by_graph         -> present in the graph-expansion ranking (pre-cap)
  expanded_rank          -> 0-based position in that ranking, if found
  survives_cap           -> its document_id is still fetched after the
                             MAX_EXPANDED_DOCS cap
  chunk_fetched          -> /search-by-doc returned at least one chunk for
                             its document
  survives_chunk_limits  -> (WP-T1c) its document_id is present among the
                             chunks execute_retrieval_plan's per-document
                             slice and prepare_chunks_for_agent's
                             max_chunks_per_doc/max_total_chunks kept, i.e.
                             chunk-count truncation, not token budgeting
                             (filled in by finalize_evidence_survival)
  reaches_final_context  -> (WP-T1c) its document_id is present among the
                             chunks that survive build_labeled_context's
                             token-budget truncation, run strictly AFTER
                             survives_chunk_limits -- these are two
                             genuinely distinct stages. Before WP-T1c this
                             field was computed from the pre-token-budget
                             chunk list, which really only measured
                             survives_chunk_limits; a document can now pass
                             chunk-count limits and still be dropped later
                             by the token budget, and that distinction is
                             exactly what WP-T1c exists to surface, so the
                             two flags must never be collapsed into one.

This is deliberately a plain dict-producing module, not an observability
framework: everything here is data already computed by hybrid_retrieve/
run_rag, just retained and reported per requested canonical_id instead of
discarded once counts are logged.
"""
from dataclasses import dataclass, asdict
from typing import Dict, List, Optional, Set

DROP_NOT_FOUND = "not_found_by_vector_or_graph"
DROP_TRUNCATED_BY_CAP = "truncated_by_max_expanded_docs"
DROP_FETCH_EMPTY = "fetch_returned_no_chunks"
# WP-T1c: DROP_FINAL_CONTEXT split into the two stages it used to conflate.
DROP_CHUNK_LIMITS = "dropped_by_chunk_count_limits"
DROP_TOKEN_BUDGET = "dropped_by_token_budget"


@dataclass(frozen=True)
class EvidenceSurvival:
    canonical_id: str
    document_id: Optional[str]
    found_by_vector: bool
    found_by_graph: bool
    expanded_rank: Optional[int]
    survives_cap: bool
    chunk_fetched: bool
    survives_chunk_limits: Optional[bool]
    reaches_final_context: Optional[bool]
    drop_reason: Optional[str]

    def as_dict(self) -> Dict[str, object]:
        return asdict(self)


def compute_partial_evidence_survival(
    *,
    target_canonical_ids: Set[str],
    seed_canonical_ids: Set[str],
    expanded_ranked: List[str],
    canonical_to_doc: Dict[str, str],
    expanded_doc_ids_used: List[str],
    fetched_doc_ids_with_chunks: Set[str],
) -> List[Dict[str, object]]:
    """
    Build one EvidenceSurvival per target canonical_id, covering every stage
    up to (but not including) chunk-limit/token-budget truncation -- those
    two stages happen later in run_rag, after prepare_chunks_for_agent and
    build_labeled_context respectively, and are filled in by
    finalize_evidence_survival. Returns plain dicts (via as_dict) so the
    result can travel through retrieval_plan_dict/RAGResult.retrieval_plan
    without any extra serialization step.
    """
    rank_by_cid = {cid: i for i, cid in enumerate(expanded_ranked)}
    used_doc_ids = set(expanded_doc_ids_used)

    entries: List[EvidenceSurvival] = []
    for cid in sorted(target_canonical_ids):
        found_by_vector = cid in seed_canonical_ids
        expanded_rank = rank_by_cid.get(cid)
        found_by_graph = expanded_rank is not None
        document_id = canonical_to_doc.get(cid)
        survives_cap = bool(document_id and document_id in used_doc_ids)
        chunk_fetched = bool(
            document_id and document_id in fetched_doc_ids_with_chunks
        )

        drop_reason: Optional[str] = None
        if not found_by_vector and not found_by_graph:
            drop_reason = DROP_NOT_FOUND
        elif found_by_graph and not found_by_vector and not survives_cap:
            drop_reason = DROP_TRUNCATED_BY_CAP
        elif survives_cap and not found_by_vector and not chunk_fetched:
            drop_reason = DROP_FETCH_EMPTY

        entries.append(
            EvidenceSurvival(
                canonical_id=cid,
                document_id=document_id,
                found_by_vector=found_by_vector,
                found_by_graph=found_by_graph,
                expanded_rank=expanded_rank,
                survives_cap=survives_cap,
                chunk_fetched=chunk_fetched,
                survives_chunk_limits=None,
                reaches_final_context=None,
                drop_reason=drop_reason,
            )
        )
    return [e.as_dict() for e in entries]


def finalize_evidence_survival(
    partial: List[Dict[str, object]],
    chunk_limited_document_ids: Set[str],
    final_context_document_ids: Set[str],
) -> List[Dict[str, object]]:
    """
    Fill in survives_chunk_limits and reaches_final_context (WP-T1c), now
    two distinct, sequentially-checked stages instead of one:

    - `chunk_limited_document_ids`: document_ids present after
      execute_retrieval_plan's per-document slice and
      prepare_chunks_for_agent's max_chunks_per_doc/max_total_chunks
      truncation (chunk-count limits), BEFORE build_labeled_context's
      token-budget truncation runs.
    - `final_context_document_ids`: document_ids present after
      build_labeled_context's token-budget truncation, i.e. what actually
      reaches the LLM prompt.

    A document that survives chunk-count limits can still be dropped by
    the token budget -- `final_context_document_ids` is expected to be a
    subset of `chunk_limited_document_ids`, and a target can be True on
    the first and False on the second. That distinction is exactly what
    WP-T1c exists to surface, so these are never collapsed into one flag.
    A seed document that was never fetched via /search-by-doc (e.g. the
    module itself) can still reach final context through its seed chunks,
    so this only needs the two document_id sets, not the fetch-stage
    flags.
    """
    finalized: List[Dict[str, object]] = []
    for entry in partial:
        doc_id = entry.get("document_id")
        survives_chunk_limits = bool(doc_id and doc_id in chunk_limited_document_ids)
        reaches_final_context = bool(
            doc_id and doc_id in final_context_document_ids
        )
        drop_reason = entry.get("drop_reason")
        if drop_reason is None and not survives_chunk_limits:
            drop_reason = DROP_CHUNK_LIMITS
        elif drop_reason is None and not reaches_final_context:
            drop_reason = DROP_TOKEN_BUDGET
        finalized.append(
            {
                **entry,
                "survives_chunk_limits": survives_chunk_limits,
                "reaches_final_context": reaches_final_context,
                "drop_reason": drop_reason,
            }
        )
    return finalized
