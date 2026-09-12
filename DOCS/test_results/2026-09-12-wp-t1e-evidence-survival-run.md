---
title: "WP-T1e: Evidence-Survival Question Set — First Live Run"
date: 2026-09-12
type: test-result
status: complete
issue: "#100"
tags:
  - rag
  - evaluation
  - retrieval
  - evidence-survival
  - tailscale
  - contamination
related:
  - "[WP-T1 planning doc](/DOCS/audit/WP-T1-retrieval-evidence-trace.md)"
  - "[Evidence-survival question set](/DOCS/evaluations/2026-09-07-evidence-survival-question-set.md)"
  - "[2026-09-07 current-state retrieval audit](/DOCS/audit/2026-09-07-current-state-retrieval-audit.md)"
---

# WP-T1e: Evidence-Survival Question Set — First Live Run

Per explicit instruction for this run: **the frozen 8-question candidate set was run as-is against
the currently-ingested corpus, with no preemptive re-ingestion or answer-key refresh.** Where a
finding below looks like corpus staleness rather than a retrieval defect, that is called out
explicitly rather than silently worked around. This is condition 1 only ("current production
retrieval/context path, as deployed today, no changes"), one repetition — not the full 8×3×3
matrix `DOCS/evaluations/2026-09-07-evidence-survival-question-set.md`'s Experiment Matrix
describes. Scaling to more conditions/reps is a follow-up decision, not made here.

## Setup

- Executed from a local machine (no GPU) with `rag_orchestrator`'s `run_rag()` called in-process,
  `INGESTION_SERVICE_URL`/`VECTOR_STORE_URL`/`LLM_SERVICE_URL`/`OLLAMA_BASE_URL` pointed at the
  Tailscale-reachable production instance (`100.105.24.12`, ports 8001/8002/8003/11434) — this is
  the same live stack `DOCS/audit/00-Audit-Overview.md` records as `prod-2026-09-12`.
- Model: default alias, resolved to `ollama/Qwen3:4b` for every call (confirmed via
  `evidence_trace`/logs; no `provider`/`model` override was passed).
- Repos used exactly as currently ingested there, **not re-ingested for this run**:
  - `rag-foundry-universal` — repo_id `f7641840-ba13-5f9d-9ae6-87e1f924709d`, ingested
    2026-09-09 (i.e. after WP-T1a-d's source changes to `service.py`/`traversal_selector.py`/
    `evidence_trace.py` were only merged 2026-09-12 — **the ingested corpus predates this
    session's own WP-T1 code**, which is itself a live example of exactly the staleness this WP
    exists to make visible).
  - `TradeForge` (whole monorepo, not just `frontend/`) — repo_id
    `d2fcf1f0-b934-5b74-b7ac-564dd8759d81`.
- Used WP-T1a-d's instrumentation directly: `run_rag(..., trace_canonical_ids={...})` per
  candidate's declared target canonical_id(s), reading `result.retrieval_plan["evidence_trace"]`
  and `result.retrieval_plan["final_context_manifest"]`.
- **Pre-flight canonical_id check** (free, no LLM cost): confirmed via
  `GET /v1/graph/repos/{repo_id}/nodes?canonical_ids=...` that all Python-side candidates' target
  canonical_ids exist as recorded. Candidate 5's recorded canonical_id
  (`src/operationalContext.ts#upsertAdvisoryContext`) does **not** exist — the actual ingested path
  is `frontend/src/operationalContext.ts#upsertAdvisoryContext`, because this instance ingested the
  whole `TradeForge` monorepo, not the `frontend/` subdirectory the question-set doc assumed.
  Corrected for tracing purposes below; **flagged as a corpus/candidate-record mismatch, not
  silently fixed in the question-set doc itself.**

## Two findings that qualify every result below

### 1. The evaluation corpus contains its own answer key

`DOCS/evaluations/2026-09-07-evidence-survival-question-set.md` — the document listing every
candidate's exact expected answer — is itself part of `rag-foundry-universal`'s ingested corpus,
and **was retrieved as a source for 6 of the 7 Python-repo candidates** (all except Candidate 9,
where it was retrieved too, in fact — every Python candidate hit this doc). `DOCS/audit/
2026-09-07-current-state-retrieval-audit.md` (which also restates several candidates' reasoning)
was retrieved for 3 candidates as well.

This is the same failure mode `DOCS/audit/00-Audit-Overview.md`'s 2026-08-30 status entry already
recorded once for `DOCS/test_results/*.md` ("this repo's own eval docs are now part of its ingested
corpus and get retrieved as sources for the very questions they document the answers to") — it now
also applies to the newer `DOCS/evaluations/` bucket. **This invalidates answer-correctness grading
for every Python-repo candidate in this run**: a correct-looking answer may be the model deriving
it from real source, or the model echoing the leaked expected-answer text verbatim — the two are
indistinguishable from the answer text alone. The TypeScript candidate (5, against the `TradeForge`
repo) was not contaminated this way, since the question-set doc lives in the other repo's corpus.

**Not fixed here, per instruction.** Filed as issue #106 for a future decision (exclude
`DOCS/evaluations/`/`DOCS/audit/*-audit.md`/`DOCS/test_results/` from self-ingestion, or accept the
contamination and always evaluate cross-repo instead).

### 2. The evidence trace can misreport a document as dropped when it actually survived

Candidate 5's target (`frontend/src/operationalContext.ts#upsertAdvisoryContext`) traced as
`found_by_vector=true` but `document_id=null`, `survives_chunk_limits=false`,
`reaches_final_context=false`, `drop_reason=dropped_by_chunk_count_limits`. Cross-checking the same
request's `final_context_manifest` shows that document **did** reach final context (2 chunks, 290 +
545 chars, `selection_reason: "seed"`) — the canonical_id was independently confirmed to exist via
the graph API before this run. The trace's `canonical_to_document_map_http` lookup silently failed
to resolve this one canonical_id to a document_id even though it was in the seed set that lookup
was called with, so every downstream flag that depends on `document_id` (`survives_cap`,
`chunk_fetched`, `survives_chunk_limits`, `reaches_final_context`) was computed against `None` and
came out uniformly (and incorrectly) `false`.

**Not fixed here, per instruction — this is instrumentation code WP-T1 itself just built, and the
same "record findings first" discipline applies to it.** Filed as issue #107.

## Per-candidate results

| # | Name | Repo | Target(s) found? | Cap/chunk/token survival | Reached final context? | Answer verdict | Classification |
|---|---|---|---|---|---|---|---|
| 1 | Tree-sitter parser/query cache | RF | graph-only, ranks 23–25 | dropped at `MAX_EXPANDED_DOCS` cap | **No** (symbol-level) / **Yes** (via coarser MODULE chunk, `base.py`, 2 chunks reached context) | Correct, substantive, matches real caching rationale | **C→H**: symbol-level evidence capped, but the containing whole-file MODULE artifact (ADR-039 embeds the whole file) carried the same text through anyway. Evidence-trace tracks the symbol-level target only — it has no visibility into a coarser sibling artifact rescuing the same text, a real trace-granularity gap. Contaminated (question-set doc retrieved as a source) — answer may partly reflect the leaked expected-answer text. |
| 2 | Evidence-survival drop-reason precedence | RF | seed hit | dropped by chunk-count limits | No | Correct (`truncated_by_max_expanded_docs`; correctly says the reason would still be recorded if never fetched) | **E** (found + seed hit, but chunk-count-limited out) or possibly a second instance of the finding-#2 bug (document_id resolution) — not independently re-verified against the manifest for this candidate. Contaminated — the question-set doc's own restated answer for this exact candidate was in the retrieved context. |
| 3 | `hybrid_retrieve`'s ranking/mapping/fetch chain | RF | `_fetch_expanded_doc_chunks`: graph-only, rank 20, capped. `hybrid_retrieve`: seed hit, survived to final context | mixed | Partial (one target reached, one capped) | **Wrong** — fabricated a generic "filter/score/rank/truncate" RAG pipeline that does not match the real four steps (rank → map → dedup/build list → slice), attributed it to "the TradeForge RAG system," and cited a TypeScript symbol (`postCreateAnnotation`) that has nothing to do with this repo or this function | **G**: `hybrid_retrieve`'s own text reached final context, yet the model still confabulated an unrelated, contamination-flavored answer instead of describing what it had. Also **C** for the second target. |
| 5 | `upsertAdvisoryContext` default-record/merge logic (TS) | TradeForge | seed hit | traced as chunk-limited (see Finding 2 — actually reached final context) | **Yes** (per manifest; trace under-reports it) | Correct — matches the real default-record/patch/force-overwrite behavior | **H**, once Finding 2's mislabel is corrected. Not contaminated (different repo's corpus). |
| 7 | IS8 doc-link match strategy | RF | seed hit | survived chunk limits | **Yes** | **Refused** — claimed the method's implementation "is not determinable from the given evidence" and that the experiment "focuses on the frontend repository," even though this query targeted this repo (RF) and the evidence was present | **G**: evidence reached final context; generation refused anyway, reasoning from contaminated cross-candidate context instead of the actually-supplied source. |
| 9 | ADR-048 vs. the actual selector (DOCUMENTS traversal) | RF | **neither target found** (`not_found_by_vector_or_graph`) | n/a | No | Landed on the factually-correct conclusion ("no, DOCUMENTS isn't auto-traversed"), but by explicit meta-reasoning about the question-set document, not from the actual `traversal_selector.py` source, which was never retrieved | **A**: genuine seed/graph retrieval miss for both symbol-level targets — this specific query wording didn't surface `select_traversal_strategies`/`execute_traversals` at all. The correct-sounding answer is not trustworthy evidence of correct retrieval. |
| 10 | Retrieval expansion/cap constants | RF | seed hit | survived chunk limits | **Yes** | **Wrong on 3 of 4 values** — answered `MAX_EXPANDED_DOCS=5` (actual 20), `MAX_TOTAL_CHUNKS=100` (actual 50), `MAX_CONCURRENT_DOC_FETCHES=10` (actual 8); only `EXPANDED_DOC_CHUNKS=3` was right. Justified the wrong numbers by citing "the TradeForge codebase" and irrelevant reasoning borrowed from Candidate 7's write-up | **G**: this is the question-set's own declared "sanity floor" easy control ("if this fails, no other result in the batch should be trusted") — the correct config text reached final context, and generation still fabricated three of four values. The clearest, least ambiguous generation-quality failure in this run. |
| 11 | Same-priority tie-break order | RF | **seed hit** (the function itself, not via graph expansion) | survived chunk limits | **Yes** | Correct, matches the real `(best_strategy_index, -seed_hits, canonical_id)` tie-break and its alphabetical-late implication | **H**, but contaminated — the question-set's own write-up for this exact candidate was also in the retrieved context, so this cannot be told apart from answer-key echoing. |

## What this run actually supports

- **The evidence-survival trace mechanically works end-to-end** against a live, real deployment —
  `trace_id`, `expansion_metadata`, `chunks_requested_by_document`/`chunks_returned_by_document`,
  `survives_chunk_limits` vs. `reaches_final_context`, and `final_context_manifest` all populated
  correctly for 7 of 8 candidates, and the one place they disagreed (Candidate 5) pointed straight
  at a real bug in the trace's own document-ID resolution, not noise.
- **Cap loss (category C) is still real and reproducible on live data**, independent of the
  synthetic fixtures `test_evidence_survival.py`/`test_expansion_caps.py` already cover (Candidates
  1 and 3's second target) — consistent with issue #91's still-open finding, on this session's own
  source files this time rather than a historical example.
- **A genuine seed/graph retrieval miss (category A)** occurred for Candidate 9 — worth revisiting
  once corpus contamination is addressed, since right now it's impossible to tell whether the query
  wording, the corpus, or something else caused it.
- **Two clean generation failures (category G) survive the contamination caveat**: Candidates 7 and
  10 both had the correct evidence in the final context and still produced wrong or refused
  answers. Candidate 10 in particular is the question-set's own designated sanity-floor control.
  This is the strongest actionable signal from this run: **retrieval evidence reaching the prompt
  is necessary but not sufficient — this deployment's default model (`Qwen3:4b`) fails to use
  correctly-supplied evidence on at least one narrow-logic question and one trivial fact lookup.**
- **Per this WP's decision principle** (`DOCS/evaluations/2026-09-07-evidence-survival-question-set.md`
  §"Decision principle"): a code or architecture change is justified only when the same failure
  stage recurs on at least two independent questions. Category G recurred twice (7, 10); category C
  recurred twice (1, 3). Neither category A nor the trace bug (Finding 2) has a second
  confirmed instance yet in this run.

## Explicitly not done here

- Not re-ingested either repo, and not refreshed any candidate's recorded canonical_id/line-number
  references against current source, per instruction — staleness is reported, not corrected.
- Not run conditions 2/3 (diagnostic cap-relaxed control, clean-context replay) or the 3 generation
  repetitions the full Experiment Matrix specifies — this is a single condition-1 pass.
- Not filed a fix for the `MAX_EXPANDED_DOCS` cap loss (issue #91 already tracks that) or for the
  corpus contamination / trace resolution bug found here (issues #106 / #107 instead) — per the
  decision principle above, this run only reconfirmed one occurrence of each open pattern.

## Related issues

- #91 (open) — same-relation-type cap loss; Candidates 1/3 reconfirm the underlying cap mechanism
  on live data, not a new instance of #91's specific same-relation-type overload shape.
- #106 (new) — `DOCS/evaluations/`/`DOCS/audit/*-audit.md` self-ingestion contamination.
- #107 (new) — evidence-trace `canonical_to_document_map_http` resolution can silently return
  `document_id: null` for a canonical_id confirmed to exist, causing false-negative survival flags.
