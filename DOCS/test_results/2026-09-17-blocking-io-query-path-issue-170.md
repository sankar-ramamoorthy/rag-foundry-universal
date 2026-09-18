---
title: "WP-R7 PR 2: query-path blocking I/O offload (embed, rerank, graph cache)"
date: 2026-09-17
type: test-results
status: partial
tags: [async, event-loop, retrieval, reranking, graph-cache, acceptance]
related:
  - "[Repository architecture audit (A9)](/DOCS/audit/2026-09-16-repository-architecture-audit.md)"
  - "[R7 issue spec](/specs/005-production-correctness/issues/async.md)"
  - "[PR 1 test results](/DOCS/test_results/2026-09-17-blocking-io-delete-vectors-issue-170.md)"
  - "[R5 generation-aware graph cache](/DOCS/test_results/2026-09-17-generation-aware-cache-issue-168.md)"
---

# WP-R7 PR 2 verification — #170 (query path)

## Scope and current result

Second of two PRs scoped for #170 (WP-R7). Moves the remaining
synchronous work audit A9 identified on the query path off the event
loop: `embed_query`, optional reranking, and the codebase graph-cache
fetch/check that `hybrid_retrieve`'s graph expansion depends on
(`get_cached_graph`, which #168/WP-R5 made a per-call synchronous
generation check plus a synchronous full-graph HTTP fetch on a cache
miss). No behavior change, no new abstractions, no async client
rewrites. PR 1 (delete_repo + vector-service routes,
[#185](https://github.com/sankar-ramamoorthy/rag-foundry-universal/pull/185))
is CI-green but not yet merged; this PR does not depend on it landing
first (disjoint files).

Not yet merged or run against production. No Linux/live-stack
verification is claimed here — local unit evidence only.

## What changed

- `rag_orchestrator/src/core/service.py`:
  - `run_rag`: `query_embedding = embed_query(query, embedder)` →
    `await asyncio.to_thread(embed_query, query, embedder)`.
  - `run_rag`: the optional-reranker `rerank_chunks(...)` call →
    `await asyncio.to_thread(rerank_chunks, ...)`.
  - `hybrid_retrieve`: `ranking = _rank_expanded_canonical_ids(...)` →
    `await asyncio.to_thread(_rank_expanded_canonical_ids, ...)`. This is
    the one call that reaches `get_cached_graph`, so it's also where
    #168/WP-R5's per-call generation check gets offloaded. `get_cached_graph`
    itself (and its `_repo_graphs_lock`, a `threading.Lock`) is untouched —
    it was already thread-safe for concurrent callers; this PR only
    changes which thread calls it.
- `rag_orchestrator/src/core/simple_service.py`:
  - `run_simple_rag`: same `embed_query` and `rerank_chunks` offloads as
    above. `run_simple_rag` does not use the codebase graph cache (its
    document-DEFINES expansion is a separate, still-synchronous
    `requests.get` in `_list_outgoing` — out of this PR's stated scope,
    not touched; audit A9 did not name it specifically, and the user's
    scope list for PR 2 was embed/rerank/graph-cache only).

## R5 (#168) interaction — explicitly verified unchanged

`get_cached_graph` resolves the current generation once per call and
uses it consistently for that call (R5's guarantee against mixing two
generations' graph evidence within one query). This PR does not touch
`get_cached_graph`, `get_repo_generation`, or `_repo_graphs`/
`_repo_graphs_lock` — it only moves the *caller* (`_rank_expanded_canonical_ids`,
and transitively `hybrid_retrieve`) onto a worker thread via
`asyncio.to_thread`. Since `_repo_graphs_lock` is a `threading.Lock` (not
an asyncio lock), it was already safe to call from a non-event-loop
thread; no synchronization change was needed or made. One generation is
still resolved exactly once per `hybrid_retrieve` call, on whichever
thread that call now runs on.

## Finite embedding timeout

The user's PR 2 instruction asked to add a finite timeout to the
synchronous Ollama embedding request "if that is already within #170's
documented scope." Checked `shared/embedders/ollama.py`: `OllamaEmbedder.embed`
already sets `timeout=(10, 120)` on its `requests.post` call, added by
#160's bounded-ingestion-memory PR (`12040f1`). `embed_query` (used by
both RAG paths) calls this same method, so the query path already has a
finite embedding deadline. No change made here — nothing to add.

## Evidence ledger

- New `rag_orchestrator/tests/test_query_path_async_offload.py` (unit,
  4 tests): each blocks one offloaded seam (`embed_query` in `run_rag`,
  `embed_query` in `run_simple_rag`, `rerank_chunks` in `run_rag`,
  `get_cached_graph` reached through `hybrid_retrieve`) with a
  `time.sleep` stand-in, runs it concurrently with an `asyncio.sleep`-based
  heartbeat via `asyncio.gather`, and asserts the heartbeat keeps ticking
  throughout — the same concurrency-proof technique as PR 1. All 4 pass.
- Full `rag_orchestrator` unit suite (via root `.venv`'s pytest, matching
  CI's `../.venv/bin/python -m pytest -q`): 166 passed, 1 skipped (the
  skip is a pre-existing live-env-var-gated A/B harness test, unrelated).
  Up from 162 passed pre-PR by exactly the 4 new tests.
- `ruff check` clean on all touched/new files. `pyright` (via root
  config) clean on `service.py`/`simple_service.py` (0 errors/warnings).
- No integration/docker-marker or Linux concurrency check run yet.

## Explicitly not claimed

- Admission control / bounded concurrency (#160/#161 scope).
- `run_simple_rag`'s `_list_outgoing` document-relationship fetch (still
  synchronous `requests.get`; not named in audit A9, not in this PR's
  agreed scope — flagged here as a related follow-up candidate, not
  fixed).
- Delete-stage or query-stage timing profiling.
- Cancellation semantics under client disconnect were not separately
  exercised.
