---
title: "WP-R7 PR 1: delete_repo and vector-service route blocking I/O offload"
date: 2026-09-17
type: test-results
status: partial
tags: [async, event-loop, ingestion, vector-store, acceptance]
related:
  - "[Repository architecture audit (A9)](/DOCS/audit/2026-09-16-repository-architecture-audit.md)"
  - "[R7 issue spec](/specs/005-production-correctness/issues/async.md)"
---

# WP-R7 PR 1 verification — #170 (delete + vector-service only)

## Scope and current result

First of two PRs scoped for #170 (WP-R7): moves the synchronous work in
`ingestion_service`'s `delete_repo` and `vector_store_service`'s four
`/v1/vectors` routes off the event loop via `asyncio.to_thread`. No
behavior change, no connection pooling, no admission control (that
remains #160/#161's scope), no lifecycle redesign. A second PR (embed
query / optional reranker / R5 generation-aware graph cache) is scoped
separately since it touches the query path and the #168 (WP-R5)
interaction, and is not part of this PR.

Not yet merged or run against production. No Linux/live-stack
verification is claimed here — local unit evidence only.

## What changed

- `ingestion_service/src/api/v1/repos.py`: `delete_repo`'s entire
  previous body (advisory-lock acquisition via `reserve_repo_mutation`,
  the active-ingestion check, ingestion-id enumeration, vector cleanup,
  graph-node deletion, and `ingestion_requests` deletion) is now a plain
  function `_delete_repo_sync`, called from the route via
  `await asyncio.to_thread(_delete_repo_sync, repo_id)`. Lock acquisition
  and release happen on the same worker thread — `AdvisoryGuard`'s raw
  DBAPI connection is never opened on one thread and used/closed on
  another. R3 (#166)'s ordering/locking semantics are otherwise untouched.
- `vector_store_service/src/api/v1/vectors.py`: each of `add_vectors`,
  `similarity_search`, `delete_by_ingestion`, `search_by_document` now
  calls its `PgVectorStore` method via `asyncio.to_thread` instead of
  directly. `PgVectorStore` opens a fresh synchronous `psycopg.connect`
  per call (confirmed at `pgvector_store.py:75,215,266,288`); this PR only
  moves that call off the loop, it does not pool connections.

## Evidence ledger

- New `ingestion_service/tests/api/test_repos_delete_async_offload.py`
  (unit, mocked collaborators): mocks `HttpVectorStore.delete_by_ingestion_id`
  to block for 0.3s via `time.sleep`, runs `delete_repo` concurrently with
  an `asyncio.sleep`-based heartbeat coroutine, and asserts the heartbeat
  keeps ticking throughout — i.e. the blocking call did not run on the
  event loop. 1 test, passes.
- Existing `ingestion_service/tests/api/test_repos_delete.py` (6 tests:
  idempotency, lock rejection, active-ingestion rejection, ordering,
  partial-failure handling) passes unchanged — the offload is transparent
  to request/response shape and error semantics.
- New `vector_store_service/tests/api/test_vectors_async_offload.py`
  (unit, mocked `PgVectorStore`): same heartbeat-concurrency technique
  against `similarity_search`, `delete_by_ingestion`, and `add_vectors`
  (3 tests), plus 2 semantics-preservation tests confirming
  `similarity_search`/`search_by_document` still return the same shaped
  results the store returns. 5 tests, passes. No prior route-level test
  file existed for `vectors.py`; this is new coverage, not a rewrite.
- `ingestion_service` full unit suite: 310 passed, 1 skipped, 72
  deselected (this run, on this branch; prior-baseline count on `main`
  was not independently re-measured this session). 5 pre-existing
  `test_gradio_delete_repo.py` failures
  (`AttributeError: module 'gradio' has no attribute 'Dropdown'`)
  reproduce identically on `main` before this change — confirmed via
  `git stash`; unrelated to this PR.
- `vector_store_service` unit suite: 27 passed, 12 deselected (up from a
  smaller count pre-PR by the 5 new tests).
- `ruff check` clean on all touched/new files. Focused `pyright` clean on
  `repos.py` and `vectors.py` (0 errors/warnings).
- No integration/docker-marker or Linux concurrency check run yet — the
  heartbeat tests above are the acceptance-criteria concurrency proof at
  unit level (audit A9's "hold a fake slow ... call while an unrelated
  ... request succeeds" pattern), not a real-Postgres or production
  reproduction of the recorded freeze.

## Explicitly not claimed

- Connection pooling for `PgVectorStore` (still opens a connection per
  call; this PR only moves that call off the loop).
- Admission control / bounded concurrency (#160/#161 scope).
- Delete-stage timing profiling (A9's other, unresolved action item).
- Embed-query, reranker, or graph-cache offload — PR 2.
- Cancellation semantics under client disconnect were not separately
  exercised.
