---
title: "Issue 254 seed-ranking and graph-expansion checkpoint"
date: 2026-10-11
type: test-result
status: partial-diagnostic-checkpoint
tags: [retrieval, diagnostics, issue-254, reproducibility, graph-expansion]
related:
  - "[Issue #254](https://github.com/sankar-ramamoorthy/rag-foundry-universal/issues/254)"
  - "[Pinned R1/R2 replay](/DOCS/test_results/2026-10-11-issue-254-pinned-replay.md)"
  - "[Diagnostic checkpoint](/DOCS/test_results/2026-10-11-issue-254-diagnostic-checkpoint.md)"
  - "[Agent Execution Boundaries](/DOCS/deployment/agent-execution-and-verification.md)"
  - "[ADR-054](/DOCS/adr/ADR-054-evaluation-dataset-isolation-and-generalization.md)"
---

# Seed-ranking and graph-expansion checkpoint

Follow-up to the [pinned R1/R2 replay](/DOCS/test_results/2026-10-11-issue-254-pinned-replay.md).
Bounded, read-only investigation: no deployment, no retrieval-behavior
change, no parameter tuning, no new diagnostic endpoint. Every call below
used an existing HTTP endpoint (remote Ollama `/api/embed`, `vector_store_service
/v1/vectors/search` and `/v1/vectors/search-by-doc`, `ingestion_service
/v1/graph/repos/{repo_id}/nodes` and `/v1/repos/{repo_id}/generation`) with
inputs reproduced exactly from the orchestrator code paths already read.

Provenance held constant throughout: `repo_id=863e770d-651e-5bc5-83d1-a1409693e707`,
`generation_id=24f827d7-a33b-45f7-93f4-ff6e5eaf3856` (= the graph snapshot
identity, per ADR-051's `(repo_id, generation_id)` cache key),
`commit_sha=f854303e6e44ff95d94792d24868442a28080ba2`. Re-checked via
`/v1/repos/.../generation` immediately before and after every probe below;
unchanged throughout. Retrieval parameters: `top_k=10`, `rerank=false`,
`claim_type=repository_overview`, `trace_canonical_ids` including
`py_mono/agent/agent.py#Agent.run`. Traversal-strategy selection is a
deterministic keyword-regex rule table (`traversal_selector.py`, no LLM
router per ADR-045) over the query text, which is byte-identical across
every run in this checkpoint — the selected strategy is therefore
guaranteed identical and was not independently re-verified per run.

## What was ruled out (all confirmed with direct evidence)

- **Embedding model/digest** — identical. The deployed Ollama's live digest
  for `mxbai-embed-large:latest` (`468836...`) matches exactly what the
  2026-10-11 local replay recorded.
- **Orchestrator code path** — identical. `git diff f344bd5..HEAD` on
  `rag_orchestrator/src/core/service.py` touches only lines 1199+ (post-seed
  chunk-selection tracing added by the diagnostic branch); `hybrid_retrieve`'s
  seed-filter/embedding construction (lines 857–930) is byte-for-byte
  unchanged between the deployed runtime (`f344bd5`) and this checkout.
- **ANN/vector-search nondeterminism** — ruled out. The same `query_vector`
  against `vector_store_service /v1/vectors/search` with the exact seed
  filter (`source_type=code`, `repo_id`, `ingestion_id`, `k=10`) returned
  identical scores and ordering across 3 repeated calls.
- **Generation/filter-tagging defect** — ruled out for the specific files
  investigated below. `agent.py`, `agent.py#Agent.run`, `agent_backupv1.py`,
  and `agent_backupv1.py#Agent.run` are all tagged with the correct
  `ingestion_id` in their `vector_chunks` rows.

## Confirmed: current seed ranking is stable, and differs from the deployed-control capture

Two independent captures agree, hours apart: the 2026-10-11 local replay
(`run_utc` 12:53:55Z) and a fresh rerun of the same unmodified replay
harness against the live stack (this checkpoint) both return the identical
7-entry seed set for `R2_provider_switch_explicit` — `README.md`, two
`ADR-006` fragments, `agent_backupv1.py`, `main.py`, and two `specs/*.md`
fragments. Neither includes `agent.py`, `agent.py#Agent`, or
`session_manager.py`.

The deployed-control capture (`run_utc` 12:58:28Z, 5 minutes after the
local replay) returned a 10-entry seed set that **does** include `agent.py`,
`agent.py#Agent`, and `session_manager.py`, and does **not** include
`agent_backupv1.py`'s file-level entry at all (only its class, via a
different id shape).

**This is not an environment artifact** — every mechanism that could have
caused it (embedding model, code path, ANN determinism, generation
tagging) has been individually ruled out above. It is either (a) index
content that was still settling at the moment of the deployed-control
capture (this generation is `is_incremental: true`, with a
`parent_generation_id`; issue #196's incremental-reuse retagging runs as a
background step after a generation is marked ready), or (b) some other
difference specific to that one 12:58:28Z request that these artifacts do
not capture. **Unresolved** — distinguishing these requires either
historical per-row retag-completion timestamps (not exposed over HTTP) or
a new instrumented signal, both out of scope for this bounded pass.

## Confirmed: graph expansion discovers the backup's method, not the authoritative one

With the current stable 7-entry seed set, graph expansion (`expanded_canonical_ids`,
89 entries) includes `py_mono/agent/agent_backupv1.py#Agent.run` and all of
`agent_backupv1.py`'s other methods, but not `py_mono/agent/agent.py#Agent.run`
— only the bare class node `py_mono/agent/agent.py#Agent` appears for the
live file. `chunk_selection_trace` confirms `agent.py#Agent.run` is never a
candidate at any stage (empty trace rows for that canonical ID), matching
the earlier checkpoint's "neither seed nor graph candidate" finding.

This is a **directly observed mechanism**, not an inference: `agent_backupv1.py`
is itself a vector seed in the current state, so DEFINES/CALL-edge expansion
from that seeded file pulls in all its methods for free, including `.run`.
`agent.py` is not seeded, so nothing pulls its `.run` method in by the same
path.

## Confirmed: the backup file genuinely outranks the authoritative file on cosine similarity

Direct `vector_store_service /v1/vectors/search-by-doc` calls, same query
embedding, same generation, both files' and both methods' document rows
checked explicitly — all four correctly tagged with the live
`ingestion_id`:

| Artifact | Best chunk score | vs. current top-10 seed cutoff (0.8160) |
| --- | --- | --- |
| `agent_backupv1.py` (file, chunk 0) | 0.8326 | above — this is why it seeds |
| `agent.py` (file, chunk 0) | 0.7926 | below — correctly excluded by rank |
| `agent_backupv1.py#Agent.run` (chunk 4) | 0.7322 | below |
| `agent.py#Agent.run` (chunk 7) | 0.7154 | below |

This rules out a filtering or generation-tagging defect for these two
files specifically: `agent.py` is present, correctly tagged, and simply
scores lower than `agent_backupv1.py` against this query, at both file
and method granularity. **Not established**: whether `agent.py` scored
higher at the deployed-control capture's moment (5 minutes before the
local replay) — current scores describe only the present state, per the
instruction not to infer historical drift from current cosine scores
alone.

## Classification

- **Confirmed failure, independent of the historical deployed/local
  discrepancy:** a stale backup file present in the ingested repository
  (`agent_backupv1.py`) can outrank the authoritative implementation
  (`agent.py`) on cosine similarity for a query naming the authoritative
  file's own symbols, and graph expansion then amplifies that mistake by
  surfacing the backup's methods instead of the real ones. This is a
  **retrieval-architecture / evidence-discovery limitation** (seed quality
  gates everything downstream), not a chunk-budget or final-context
  truncation problem — matches the earlier checkpoint's "neither seed nor
  graph candidate" finding, now with a confirmed mechanism.
- **Unresolved, separate question:** whether the deployed-control capture's
  different seed set (including `agent.py`) reflects index-state drift
  during incremental-generation settling, or something else specific to
  that one request. Not provable from existing HTTP evidence.

## Candidate corrective actions (not implemented)

Recorded for a future decision, not a commitment to any of them:

- Seed-stage demotion or exclusion of known backup/duplicate-named source
  files (heuristic, repo-specific, fragile).
- A tie-break or authority signal that prefers the currently-imported/
  referenced file over an unreferenced duplicate when both are candidates
  (would need a structural signal, e.g. import-graph reachability from an
  entry point, not just lexical similarity).
- Treat this as a corpus-hygiene problem instead: flag or exclude files
  that look like backups (naming convention, e.g. `*_backupv1.py`) at
  ingestion time rather than at retrieval time.
- No action: this may be an acceptable, rare failure mode for repositories
  that keep literal duplicate/backup source files in version control.

## Validation

Read-only throughout. No production deployment, re-ingestion, code change,
PR, merge, or issue closure. No ranking/budget/prompt parameter was
changed or tuned. Under ADR-054, all data here is development/diagnostic,
not a held-out generalization result.
