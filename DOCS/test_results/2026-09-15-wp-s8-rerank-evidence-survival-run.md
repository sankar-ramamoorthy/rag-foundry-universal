---
title: "WP-S8: Rerank on/off vs. the frozen evidence-survival candidate set"
date: 2026-09-15
type: test-result
status: complete
issue: "#152"
tags:
  - rag
  - evaluation
  - retrieval
  - reranker
  - evidence-survival
  - tailscale
  - contamination
related:
  - "[Evidence-survival question set](/DOCS/evaluations/2026-09-07-evidence-survival-question-set.md)"
  - "[WP-T1e first live run](/DOCS/test_results/2026-09-12-wp-t1e-evidence-survival-run.md)"
  - "[Reranker-built-ahead-of-gate decision](/DOCS/notes/20260915-reranker-built-ahead-of-evaluation-gate-decision.md)"
  - "[Retrieval technique decision gates](/DOCS/audit/09-Retrieval-Technique-Decision-Gates.md)"
  - "[Issue #141](https://github.com/sankar-ramamoorthy/rag-foundry-universal/issues/141)"
  - "[Issue #145](https://github.com/sankar-ramamoorthy/rag-foundry-universal/issues/145)"
---

# WP-S8: Rerank on/off vs. the frozen evidence-survival candidate set

Per the decision recorded in `DOCS/notes/20260915-reranker-built-ahead-of-evaluation-gate-decision.md`
(issue #152), the next step was to deploy the flag-gated reranker to the Tailscale stack and re-run
the frozen 8-question evidence-survival set (`DOCS/evaluations/2026-09-07-evidence-survival-question-set.md`,
candidates 1, 2, 3, 5, 7, 9, 10, 11) with `rerank=true` vs. `rerank=false`, to gather the A/B evidence
the reranker decision gate asks for. **Result: this run cannot supply that evidence for the
`rag-foundry-universal` side of the set.** A pre-existing, still-open retrieval defect (issue #141)
means the real source for 6 of the 7 Python-repo candidates never enters the candidate pool the
reranker reorders, in either condition. The one clean candidate (TradeForge, #5) gives a single usable
data point, not enough to decide anything per this project's decision principle.

## Setup

- Deployed: `rag_orchestrator` (commit at `main`, including WP-S8's `#153`) redeployed to the
  Tailscale-reachable production instance (`100.105.24.12`, ports 8001-8003/8004/11434).
- Both repos already freshly ingested there as of 2026-09-15 (same day, post issue #150's HNSW fix):
  `rag-foundry-universal` — repo_id `f7641840-ba13-5f9d-9ae6-87e1f924709d`; `TradeForge` (whole
  monorepo) — repo_id `d2fcf1f0-b934-5b74-b7ac-564dd8759d81`.
- Executed via the public `/v1/rag` HTTP endpoint (not in-process), one call per (candidate, rerank)
  pair, `top_k=5`, no `trace_canonical_ids` (not exposed over HTTP) — evidence read from
  `retrieval_plan.final_context_manifest`, which every response includes regardless of tracing.
  16 live calls total (8 candidates x 2 conditions). Script: ad hoc, not committed (scratchpad).
- Model: default alias, resolved to `ollama/Qwen3:4b` for every call (confirmed via `model_used`).
- "Real source" below means any `final_context_manifest` entry whose `canonical_id` is *not* under
  `DOCS/evaluations/`, `DOCS/audit/`, or `DOCS/test_results/` — i.e. not this project's own
  eval/meta documentation.

## Headline finding: candidate pool contamination, not just answer-grading contamination

`DOCS/notes/20260912-self-ingestion-eval-corpus-policy.md` previously characterized self-ingestion
contamination as invalidating *answer-quality grading* (the eval doc gets retrieved *alongside* real
source, so a correct-looking answer might be echoed rather than derived). This run found something
materially worse for the current corpus: for 6 of the 7 `rag-foundry-universal` candidates, **zero**
real-source chunks reached final context, at either `k=50` (no rerank) or the post-rerank `k=10`.
Not outranked — absent. This matches issue #141's finding (filed earlier the same day, with direct DB
verification) but this run shows it is not scoped to that issue's one repro query; it is the default
outcome for nearly the whole frozen set today.

| # | Repo | Real-source chunks, no rerank (of 50) | Real-source chunks, reranked (of 10) | Target canonical_id present? |
|---|---|---:|---:|---|
| 1 | RF | 0 | 0 | No (either condition) |
| 2 | RF | 0 | 0 | No (either condition) |
| 3 | RF | 0 | 0 | No (either condition) |
| 5 | TF | n/a (not contaminated corpus) | n/a | **Yes (both conditions)** |
| 7 | RF | 0 | 0 | No (either condition) |
| 9 | RF | 0 | 0 | No (either condition) |
| 10 | RF | some (target present) | 0 | **Yes at rerank=false, No at rerank=true** |
| 11 | RF | 0 | 0 | No (either condition) |

Candidate 10 is the one case where the target survived at all on the RF side, and reranking is what
removed it: the cross-encoder, scored against a query whose exact wording appears verbatim inside
`DOCS/evaluations/2026-09-07-evidence-survival-question-set.md` (because that document literally
contains this frozen question set), preferred the contaminating doc's near-duplicate text over the
real `rag_orchestrator/src/core/config.py#Settings` chunk. This is a real, reproducible instance of
reranking making retrieval worse — but it is a symptom of #141's contamination, not evidence about
reranking quality in general; it would not occur against an uncontaminated corpus.

## Reranker infrastructure itself: verified working end-to-end, live

Independent of the contamination finding, WP-S8's plumbing worked correctly on every one of the 16
calls:

- `reranked` response field matched the requested `rerank` value in all 16 cases.
- `rerank=true` consistently cut `final_context_manifest` from the pre-cap pool down to
  `RERANK_TOP_K=10`, as configured.
- Latency dropped substantially under rerank for 6 of 7 RF candidates (e.g. candidate 9: 73.2s ->
  12.9s; candidate 3: 74.7s -> 22.2s) — expected, since generation runs over far fewer tokens
  (`tokens_after_budget` dropped roughly 2200 -> 600 in most RF cases). Candidate 5 (TradeForge, the
  one uncontaminated case with real diverse candidates) instead went *up* under rerank (49.5s ->
  66.3s) — consistent with the cross-encoder doing real discriminative work over a genuinely varied
  pool, unlike the RF cases where it is mostly reordering near-duplicate contamination text.

This confirms the reranker is safe to keep deployed (flag off by default, no behavior change), and
that per-request `rerank` override works for future A/B use once the blocking issue below is fixed.

## Candidate 5 (TradeForge, the one clean comparison)

Target `frontend/src/operationalContext.ts#upsertAdvisoryContext` reached final context in both
conditions (2 manifest entries at `rerank=false`, 1 at `rerank=true` — reranking narrowed but did not
drop it). This is a genuine, uncontaminated on/off data point, and it is a positive one (reranking
didn't hurt here) — but it is one question. Issue #145, filed the same day against this exact
candidate, separately found a *generation*-stage failure on this query (correct chunk retrieved, LLM
still hedged/refused before eventually answering correctly) — worth noting as a reminder that survival
to `final_context_manifest` is necessary but not sufficient, consistent with WP-T1e's Category G
finding from the 2026-09-12 run.

## Why the evaluation gate is still not satisfied

Per `DOCS/evaluations/2026-09-07-evidence-survival-question-set.md`'s decision principle: *a change is
justified only when the same failure stage is demonstrated on at least two independent questions.*
This run cannot produce that kind of evidence for reranking specifically, because 6 of 7 RF candidates
never gave the reranker a real candidate to promote or demote in the first place — there is no
retrieval-stage signal about reranker quality available on the current `rag-foundry-universal` corpus,
only more confirmation of issue #141. The single TradeForge data point is necessary-but-not-sufficient
by the same principle.

## Stale doc flagged, not silently fixed

`DOCS/audit/09-Retrieval-Technique-Decision-Gates.md`'s doc-type-tie-break row currently states that a
2026-09-15 live attempt found the original issue #141 base.py repro "no longer exhibits the failure at
all, flag on or off," attributing it to same-day corpus drift. This run (also 2026-09-15, timestamped
after issue #141 was filed) reproduces the failure again for the identical query, at full severity
(zero real chunks, not a near-tie). Both observations are from the same day against a corpus that was
being re-ingested/edited during that day — "no longer occurs" claims from unpinned same-day live
checks are not stable evidence. Flagged in that document rather than overwritten, per this project's
convention for eval-doc resolution updates (see the 2026-09-12 WP-T1e doc's own precedent).

## What this run recommends

- **Do not use this run, or any future run against the current `rag-foundry-universal` self-ingested
  corpus, to decide `RERANK_ENABLED`'s default.** Fix or work around issue #141 first — either the
  `DOC_TYPE_TIE_BREAK_ENABLED` mechanism (re-verified against a pinned snapshot, not same-day drift),
  or a stronger fix per #141's own "investigation direction" section (excluding self-generated
  eval/meta documents from codebase ingestion, or an explicit artifact-role signal).
- **The TradeForge (or another non-self-ingested) corpus remains a valid test surface** for gathering
  real reranker A/B evidence in the meantime — this run's single candidate-5 data point is a
  reasonable seed for a larger uncontaminated question set, not proof of anything on its own.
- No change to `RERANK_ENABLED` (stays `False`) or `DOC_TYPE_TIE_BREAK_ENABLED` (stays `False`) is
  made by this document.

## Related issues

- #141 (open) — this run's central finding is a reconfirmation of #141 across the full frozen set,
  posted as a comment there with this document linked.
- #145 (open) — candidate 5's generation-stage hedging, orthogonal to this run's retrieval-stage focus.
- #152 (open) — the reranker implementation this run was meant to evaluate; still pending real A/B
  evidence.
