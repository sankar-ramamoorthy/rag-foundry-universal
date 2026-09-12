---
title: "WP-T1 — Retrieval Evidence Trace"
date: 2026-09-12
type: audit
status: complete
issue: "#100"
tags:
  - audit
  - retrieval
  - observability
  - evidence-survival
related:
  - "[ADR-045 — Hybrid Vector+Graph RAG](/DOCS/adr/ADR-045-hybrid-vector-graph-rag.md)"
  - "[00-Audit-Overview](/DOCS/audit/00-Audit-Overview.md)"
  - "[07-Roadmap](/DOCS/audit/07-Roadmap.md)"
  - "[2026-09-07 Current-state retrieval audit](/DOCS/audit/2026-09-07-current-state-retrieval-audit.md)"
  - "[08-RAG-Quality-Evaluation-Methodology](/DOCS/audit/08-RAG-Quality-Evaluation-Methodology.md)"
  - "[WP-T1e first live run](/DOCS/test_results/2026-09-12-wp-t1e-evidence-survival-run.md)"
---

> [!tip] Status: complete (2026-09-12)
> T1a-T1d shipped as PRs #102-#105. T1e ran the frozen 8-question evidence-survival set live
> against the production instance (Tailscale) — see
> [DOCS/test_results/2026-09-12-wp-t1e-evidence-survival-run.md](/DOCS/test_results/2026-09-12-wp-t1e-evidence-survival-run.md).
> Two new follow-up issues came out of that run: [#106](https://github.com/sankar-ramamoorthy/rag-foundry-universal/issues/106)
> (this repo's own `DOCS/evaluations/`/audit docs contaminate the corpus they evaluate) and
> [#107](https://github.com/sankar-ramamoorthy/rag-foundry-universal/issues/107) (the evidence
> trace's own canonical_id→document_id resolution can silently return null for an ID confirmed to
> exist). Neither is fixed here, per the same evidence-first discipline #89 used — both are
> deliberately separate, undecided next steps.

# WP-T1 — Retrieval Evidence Trace

> [!note] Naming
> This work package is named **WP-T1**, not `WP-Q1`, deliberately: `DOCS/audit/08-RAG-Quality-Evaluation-Methodology.md`
> already defines its own `WP-Q1`/`WP-Q2`/`WP-Q3` (chunking / retrieval / generation quality),
> executed as a single unified pass under `WP-Q0` (issue #49, closed — see
> `DOCS/test_results/2026-08-27-wp-q0-rag-quality-baseline.md`). Reusing `WP-Q1` here would create
> avoidable ambiguity across issues, commits, and this roadmap. `T` stands for **Trace**.

## Why this work, now

`DOCS/audit/00-Audit-Overview.md`'s 2026-09-12 status records production hardening as complete and
names the next unproven question explicitly:

> whether the right evidence reliably survives seed retrieval, graph expansion, caps/ranking, chunk
> fetch, token budgeting, and final context assembly.

We already have direct evidence this can fail:

- **Issue #89** (closed via PR #90): graph expansion could correctly discover authoritative
  implementation evidence that then got discarded by authority-blind ranking at the
  `MAX_EXPANDED_DOCS` cap. Fixed with relation-type-aware expansion ranking
  (`rag_orchestrator/src/retrieval/traversal_selector.py`); confirmed live (a target's rank moved
  from 24 → 12 and it began reaching final context).
- **Issue #91** (open): a second target's rank improved substantially under the #89 fix
  (137 → 88) but still didn't clear the cap — a *same-relation-type candidate overload* case that
  relation-priority ranking alone can't resolve.
- `DOCS/audit/2026-09-07-current-state-retrieval-audit.md` independently reconfirms this as the
  most important confirmed problem ("useful graph-discovered evidence is discarded before its
  content can influence selection") and its §3.1 "Investigation 1" proposes almost exactly the
  evidence-survival experiment this WP formalizes — but as a one-off manual methodology, not
  durable instrumentation.

## What already exists — this WP is smaller than it looks

Issue #89 already produced `rag_orchestrator/src/retrieval/evidence_trace.py`: an opt-in,
behavior-neutral `EvidenceSurvival` dataclass tracking, per requested `canonical_id`:

```
found_by_vector, found_by_graph, expanded_rank, survives_cap, chunk_fetched,
reaches_final_context, drop_reason
```

plus `compute_partial_evidence_survival()` / `finalize_evidence_survival()`, and
`rag_orchestrator/tests/test_evidence_survival.py` proving the instrumentation doesn't change
retrieval results. **This is real prior art for exactly the mechanism the pipeline diagram below
describes.** WP-T1's job is to complete and generalize it, not build a second, parallel
instrumentation framework beside it.

Known gaps in the current instrumentation:

- It's opt-in per a caller-supplied `target_canonical_ids` set, not automatic for every candidate
  in a query.
- No query-level `trace_id` / request identity exists anywhere in `rag_orchestrator`.
- No chunk-index-level detail (which chunk indices were requested/returned via `/search-by-doc`).
- No token-budget-stage tracking: `reaches_final_context` is computed *before*
  `build_labeled_context()`'s word-count truncation runs, so today's flag really means "survived
  chunk-count limits," not "survived the token budget." **These are two genuinely distinct stages
  and must stay separate fields** — a candidate can survive `execute_retrieval_plan`'s
  per-document slice and `MAX_TOTAL_CHUNKS`, and still be dropped later by the token budget. WP-T1
  introduces `survives_chunk_limits` as its own field, alongside (not merged into)
  `reaches_final_context`.
- No final-context manifest (exact chunks/canonical_ids that crossed into the LLM prompt, with
  token/char counts and selection reason).
- Relation type is computed transiently in `execute_traversals` / `execute_traversals_from_seeds`
  (`rag_orchestrator/src/retrieval/traversal_selector.py`) but discarded before reaching
  `retrieval_plan_dict`. `RetrievalPlan.expansion_metadata`
  (`shared/retrieval/retrieval_plan.py`) exists for exactly this but `run_rag` never populates it
  today.

## The pipeline being instrumented

```text
query
  ↓
retrieval request / filters
  ↓
seed vector candidates + near-duplicate dedup           (one stage in code: dedupe_near_identical_chunks
  ↓                                                       runs on the seed chunk list before canonical_id
selected seed documents                                  extraction — there is no separate "dedup" stage
  ↓                                                       distinct from "selected seeds")
graph expansion candidates
  ↓
relationship-aware ranking
  ↓
MAX_EXPANDED_DOCS cap
  ↓
chunk fetch (/search-by-doc)
  ↓
per-document / total chunk limits        → survives_chunk_limits (new, distinct field)
  ↓
token-budget assembly (build_labeled_context)
  ↓
final context                            → reaches_final_context (existing field, recomputed after
  ↓                                         token-budget truncation instead of before)
LLM request
  ↓
answer + reported sources
```

> [!note] `DOCUMENTS` edges are out of scope here
> `GraphAssembler` creates `DOCUMENTS` edges (doc → code links, ADR-048), but the query-time
> traversal-strategy selector (`traversal_selector.py`'s rule table) never traverses them today.
> That's a real coverage gap, but it's a *traversal* gap, not an *evidence-survival* gap — there is
> nothing to trace along a path that's never taken. It stays a separately-tracked issue, not part
> of WP-T1.

For every candidate, WP-T1 should be able to answer:

```text
Where did this canonical_id first appear?
What score/rank did it have?
Which traversal relationship discovered it?
Did it survive expansion ranking and the MAX_EXPANDED_DOCS cap?
If not, what removed it?
Were chunks fetched, and which chunk indices?
Did it survive per-document/total chunk limits (survives_chunk_limits)?
Did token budgeting remove it after that (reaches_final_context)?
Was its actual text present in the final LLM context?
Was it listed as a final source?
```

## Scope: WP-T1a – T1e

- **T1a — Audit and extend the existing `EvidenceSurvival` model.** Make tracing automatic for
  every candidate in a request, not just caller-supplied targets. Add a first-class
  `canonical_id` field to `RetrievedChunk`/agent chunk dicts (today it's buried in
  `chunk.metadata["canonical_id"]`, accessed via ad hoc helpers in
  `rag_orchestrator/src/retrieval/codebase_utils.py`). Actually populate
  `RetrievalPlan.expansion_metadata` (currently always `{}` on this path) with relation type per
  expanded document. Reuse `shared/retrieval/retrieval_plan.py`'s existing types — don't invent a
  parallel dataclass.
- **T1b — Query-level trace identity + stage events.** One `trace_id` per `/v1/rag` request,
  threaded through `run_rag` → `hybrid_retrieve` → `execute_retrieval_plan`
  (`rag_orchestrator/src/core/service.py`, `rag_orchestrator/src/retrieval/execute_plan.py`).
  Structured stage events using this project's existing plain `logging` module — no premature
  adoption of `structlog`/OpenTelemetry here; that belongs to Phase 4's `WP-E5 Observability`
  (generic ops observability across all services), kept explicitly separate.
- **T1c — Chunk/token/final-context survival instrumentation.** Chunk-index-level detail on
  `/search-by-doc` fetches (`rag_orchestrator/src/core/service.py`'s `_fetch_expanded_doc_chunks`).
  A new `survives_chunk_limits` field marking survival of `execute_retrieval_plan`'s per-document
  slice and `MAX_TOTAL_CHUNKS`. `reaches_final_context` kept as its own field, computed *after*
  `build_labeled_context()`'s token-budget truncation instead of before.
  `survives_chunk_limits` and `reaches_final_context` must remain two distinct fields.
- **T1d — Final-context manifest.** A structured pre-LLM-call record (`canonical_id`,
  `document_id`, `chunk_index`, source label, char/token count, selection reason) attached to
  `retrieval_plan_dict`, inspectable via the existing `RAGResult.retrieval_plan` field — no new API
  surface.
- **T1e — Run the preregistered evidence-survival question set.** Reuse
  `DOCS/audit/2026-09-07-current-state-retrieval-audit.md` §3.1 "Investigation 1" as the
  experiment methodology. Classify each question's evidence journey:

  ```text
  A. never retrieved
  B. retrieved as seed but filtered/deduped
  C. discovered by graph but lost in ranking/cap
  D. document survived but useful chunk did not
  E. useful chunk fetched but lost to chunk limits (survives_chunk_limits = false)
  F. useful chunk survived chunk limits but lost to token budget (reaches_final_context = false)
  G. useful evidence reached final context but answer failed
  H. evidence and answer both succeeded
  ```

  Record results in `DOCS/test_results/`, per this project's "nothing ships without its
  benchmark/eval delta recorded" rule — only after T1a–T1d ship with their own tests.

## Non-goals (explicitly deferred)

- No reranker.
- No change to `MAX_EXPANDED_DOCS` or any other cap value.
- No new traversal strategies (including not wiring up `DOCUMENTS` edges into query-time
  traversal).
- No embedding-model change.
- No chunking redesign.
- No fix for #91 itself — this WP produces the instrumentation that would inform a future #91 fix.
- No evidence-sufficiency agent loop / self-modifying retrieval.
- No dashboards (Grafana/Prometheus).
- No OpenTelemetry rollout — sequenced after this WP, as Phase 4's `WP-E5`'s eventual transport,
  once the trace *semantics* are proven here.
- Tracing must be behavior-neutral: it reads data already computed by the pipeline, and must never
  change what gets retrieved, ranked, capped, fetched, or included in context.

## Acceptance criteria

1. Every `/v1/rag` request gets one `trace_id`.
2. Every seed candidate's rank/score is recorded, with a first-class `canonical_id` field.
3. Every graph-expanded candidate is recorded with the relation type that discovered it and its
   pre-cap rank — for all candidates, not just explicitly-targeted ones.
4. Exactly which candidates `MAX_EXPANDED_DOCS` removed is recorded.
5. Which chunk indices were requested and returned by `/search-by-doc`.
6. A `survives_chunk_limits` field marks which chunks were removed by per-document/
   `MAX_TOTAL_CHUNKS` limits — distinct from item 8.
7. Token counts before/after `build_labeled_context()`'s budget.
8. `reaches_final_context` is its own field, computed after token-budget truncation.
9. A final-context manifest: exact chunks/canonical_ids composing the LLM prompt, with selection
   reason.
10. Answer + returned sources (already returned today).
11. One `trace_id` connects every stage above for a given request.
12. Tests prove tracing does not change retrieval behavior — extending the existing pattern in
    `rag_orchestrator/tests/test_evidence_survival.py` and `test_expansion_caps.py`.

## Tracking

Issue: [#100](https://github.com/sankar-ramamoorthy/rag-foundry-universal/issues/100).
