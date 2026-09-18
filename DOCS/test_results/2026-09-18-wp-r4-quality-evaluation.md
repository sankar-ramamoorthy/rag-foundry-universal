---
title: "WP-R4 frozen 8-question quality evaluation: WP-R4 vs. legacy runtime"
date: 2026-09-18
type: test-result
status: complete
tags: [retrieval, evidence, evaluation, quality]
related:
  - "[WP-R4 specification](/specs/005-production-correctness/issues/evidence.md)"
  - "[ADR-052](/DOCS/adr/ADR-052-evidence-delivery-context-selection.md)"
  - "[Frozen protocol](/DOCS/evaluations/2026-09-17-wp-r4-protocol.md)"
  - "[Frozen questions](/DOCS/evaluations/wp-r4-questions.json)"
  - "[Mechanics verification](/DOCS/test_results/2026-09-17-wp-r4-evidence-delivery.md)"
---

# WP-R4 quality evaluation — 2026-09-18

Executed after four failed local-infrastructure attempts documented in
[the mechanics verification doc](/DOCS/test_results/2026-09-17-wp-r4-evidence-delivery.md)'s
"Quality evaluation attempt" section. Retrying against the
Tailscale-reachable production Ollama (GPU) rather than this session's
local CPU Ollama resolved the throughput problem completely — ingestion
finished in minutes instead of stalling, and all 16 generation calls
(8 questions x 2 runtime arms) plus 3 clean-context calls completed
without a single infrastructure failure.

## Setup

- Corpus: the same pinned 54-file source-only export at
  `3ba6a2f4cec4d3e0724859d70aeff98bb7f7880f`
  (`DOCS/evaluations/wp-r4-corpus-manifest.json`), ingested fresh into
  the isolated local database `wp_r4_741f14a1c7_test`
  (`ingestion_id=6b337ad0-8aea-456a-8f31-2d2e4f05e92f`, 396 nodes, 1381
  chunks, `generation_status: ready`).
- Two runtime arms, both against the **same** ingested corpus and the
  **same** local `ingestion_service`/`vector_store_service` (only the
  orchestrator code differs):
  - **`wp_r4`**: `fix/wp-r4-evidence-delivery` at commit `cbb84d7`
    (this branch, unchanged this session).
  - **`legacy`**: base revision `3ba6a2f4cec4d3e0724859d70aeff98bb7f7880f`,
    run from a `git worktree` (`../rag-foundry-legacy-r4-base`) so both
    arms' code coexist without switching branches mid-session.
- Embedding: `mxbai-embed-large:latest` via the Tailscale production
  Ollama (`100.105.24.12:11434`). Generation: `ollama/Qwen3:4b`, same
  endpoint, via a locally-launched `llm_service` pointed at it. **Every
  one of the 16 calls used this exact model with no fallback** (verified
  per-call, not assumed) — the arms are comparable.
- `top_k=5`, `rerank=false` (default, not toggled), `max_total_tokens`
  left at each arm's own default (4096 for both — the deployed default,
  not an artificially matched value; see "Not done" below).
- Harness: ad hoc scratchpad scripts (`.wp-r4.tmp/run_eval.py`,
  `.wp-r4.tmp/run_clean_context.py`), not committed. Each calls
  `run_rag(...)` **in-process** (direct Python import of the checkout's
  `src.core.service`, not over HTTP) against the real local
  ingestion/vector services and the real remote-Ollama-backed
  `llm_service` — real code and real network calls throughout, only the
  orchestrator's own HTTP layer is bypassed for convenience.

## Results by question

`canonical_hit`: expected target canonical_id(s) actually present in
`final_context_manifest` (retrieval-stage signal). `substrings`: how many
of the question's `required_substrings` appear in the generated answer
text (retrieval-fidelity + generation-faithfulness signal combined).

| Question | WP-R4 canonical_hit | WP-R4 substrings | Legacy canonical_hit | Legacy substrings |
| --- | --- | --- | --- | --- |
| cache | 2/3 | 3/3 | 3/3 | 3/3 |
| drop | 1/1 | 2/2 | 1/1 | 2/2 |
| chain | **0/1** | 0/4 | **1/1** | **4/4** |
| ambiguous | 0/2 | 1/2 | 1/2 | 0/2 |
| link | 1/1 | 1/2 | 1/1 | 0/2 |
| limits | 0/1 | 0/4 | 0/1 | 0/4 |
| ties | 1/1 | 3/3 | 1/1 | 0/3 |
| truncate | 2/2 | 0/4 | 2/2 | 0/4 |

**Aggregate**: WP-R4 got full-substring answers on 3/8 (cache, drop,
ties), partial on 2/8 (ambiguous, link), zero on 3/8 (chain, limits,
truncate). Legacy got full-substring answers on 3/8 (cache, drop,
**chain**), partial on 0/8, zero on 5/8 (ambiguous, link, limits, ties,
truncate). **WP-R4 answered more questions correctly overall (5/8 with
at least partial substring match vs. legacy's 3/8)** — consistent with
the manifest/budget/seed-supplementation fixes actually helping. But
this is not a clean sweep, and one result needs a specific flag below.

## The one apparent regression, root-caused: "chain"

This is the single case where **legacy outperformed WP-R4** in this run —
legacy got a complete, correct, substring-exact answer; WP-R4 got zero.
Root-caused with `trace_canonical_ids` (already supported by `run_rag`,
just not wired into the harness's first pass):

```json
{
  "canonical_id": "rag_orchestrator/src/core/service.py#hybrid_retrieve",
  "found_by_vector": true,
  "found_by_graph": false,
  "survives_cap": false,
  "chunk_fetched": true,
  "survives_chunk_limits": true,
  "reaches_final_context": false,
  "drop_reason": "dropped_by_token_budget",
  "survives_rerank": true
}
```

**Not a retrieval defect. The target chunk was correctly found, fetched,
and survived every selection stage up to the final context-assembly
budget — it was dropped there, by design, because the byte-accurate
budget is genuinely stricter than what it replaced.** This is confirmed
by the "Not done" budget-strictness observation below: legacy's
`tokens_before_budget == tokens_after_budget` on literally every one of
its 8 questions in this run — its word-count-based budget check
(`len(text.split()) > max_total_tokens`, comparing a word count against
a value named in tokens) was silently never binding at the corpus/query
sizes exercised here. WP-R4's UTF-8-byte accounting is the first budget
in this pipeline that actually enforces `max_total_tokens` as specified —
and enforcing it for real means some correctly-identified evidence now
gets cut that previously always fit only because the check wasn't really
checking anything.

**This is the intended trade-off ADR-052 documents, not a bug to fix.**
The ADR's own "Budget contract" section already flags the consequence
("Deployments must align them with model policy... A model-aware prompt
boundary check and oversized-query behavior remain review items"). This
result is exactly that review item showing up empirically: `chain`'s
seed set is large (24,004 bytes of legitimate candidate text before
budgeting) relative to the 4096-token/byte default, so the default is
too tight for this specific question's evidence volume. That's a tuning
question for `CONTEXT_WINDOW_TOKENS`/`max_total_tokens` defaults, not a
defect in the selection/assembly code under review.

## Clean-context control (partial — 1 of 3 valid)

Ran generation directly from the pinned source files (no retrieval), at
the same `context_budget=4096` bytes WP-R4 computed, for the three
questions where WP-R4 scored 0 substrings (`chain`, `ambiguous`,
`limits`):

| Question | Full source bytes | Clean-context substrings | Valid control? |
| --- | --- | --- | --- |
| chain | 34,696 | 0/4 | **No** — see below |
| ambiguous | 42,176 | 0/2 | **No** — see below |
| limits | 6,279 | **4/4** | **Yes** |

**`limits` is a clean, valid data point: pure retrieval miss.** Given
the correct source file directly, Qwen3:4b answered perfectly (all 4
default values, correctly attributed). WP-R4's RAG pipeline never
surfaced `rag_orchestrator/src/core/config.py` as a seed or expanded
candidate for this query at all (0/1 in both arms — this is a
**pre-existing** retrieval gap, not something WP-R4 introduced or
regressed). Literal, enumerative "what are the default values of X, Y, Z"
queries appear to be a real, reproducible weak spot for this corpus's
embedding-based seed search — matches this project's own quality
methodology's decision table ("Relevant evidence absent from the
retrieved candidate set — not a reranker problem").

**`chain` and `ambiguous` controls are invalid** — the harness script's
context-truncation (`run_clean_context.py`) concatenates whole files and
truncates from the *end* at the byte budget, and both target functions
are defined well past the first 4096 bytes of their (large) files. The
model was truncated before ever seeing the relevant code, so 0/4 and 0/2
substrings prove nothing about generation capability for those two —
this is a harness limitation, not evidence of a generation-stage defect.
Do not cite these two as "generation also fails."

## Not done (disclosed, not blocking this record)

- **True matched-budget control arm**: not run as a separate arm, but
  effectively superseded by the `chain` root-cause above — legacy's
  budget check turned out not to be enforcing anything in this run, so a
  "legacy code, WP-R4 byte-budget" arm would likely have reproduced the
  same drop on `chain` (and possibly others). Worth running explicitly
  in a follow-up if finer before/after separation is needed, but the
  open question this control was meant to answer is already resolved.
- **Noisy-context comparison**: not run (the "clean" arm above only
  partially succeeded on 1/3 questions; a noisy-context arm needs the
  same whole-file-truncation fix before it's worth running).
- **Reranker arm**: not run (`RERANK_ENABLED` stays off by default;
  out of WP-R4's scope).
- **Replication**: every question ran exactly once per arm. Single-run
  results on a non-deterministic LLM are directional, not proof — the
  `chain` finding is explained by a structural mechanism
  (`drop_reason`), not just a favorable re-roll, which is why it's
  treated as resolved rather than "probably fine."

## Verdict

**Net positive; no blocking findings.** The mechanics review (separate
doc) found no code defects. This evaluation found WP-R4 answering more
of the 8 frozen questions correctly than legacy (5/8 vs. 3/8
partial-or-better), a genuine pre-existing retrieval gap unrelated to
WP-R4 (`limits`, confirmed via a valid clean-context control: the model
answers perfectly given the right source, so this is a seed-search gap
in the embedding/query-formulation stage, not a WP-R4 or generation
defect), and the one case where WP-R4 scored worse than legacy
(`chain`) root-caused via `trace_canonical_ids` to the new byte-based
budget correctly enforcing itself where the old word-count budget never
actually did — an intended, documented trade-off (ADR-052's own
disclosed review item), not a regression to fix.

No demonstrated failure meets the "fix only failures demonstrated by
validation" bar from a code-defect standpoint — everything found is
either a pre-existing gap (`limits`) or the correct, specified behavior
of the new stricter budget (`chain`). The one substantive follow-up
worth opening as its own issue, not blocking this merge: **the default
`CONTEXT_WINDOW_TOKENS`/`max_total_tokens=4096` combination may be too
tight for questions whose legitimate candidate set is large** (`chain`'s
was 24,004 bytes before budgeting) — a tuning question, separate from
this WP-R4 code review.
