---
title: "WP-R5 generation-aware graph cache verification"
date: 2026-09-17
type: test-results
status: partial
tags: [rag_orchestrator, caching, freshness, generation, postgres, acceptance]
related:
  - "[ADR-051](/DOCS/adr/ADR-051-generation-aware-graph-cache.md)"
  - "[R5 acceptance and tasks](/specs/005-production-correctness/issues/freshness.md)"
  - "[Programme handoff](/specs/005-production-correctness/HANDOFF.md)"
---

# WP-R5 verification — #168 (narrowed scope)

## Scope and current result

Implemented on branch `feat/168-generation-aware-graph-cache` (PR #183),
not yet merged or deployed. All four CI checks pass at head `ceabbe4`
(run [35281171853](https://github.com/sankar-ramamoorthy/rag-foundry-universal/actions/runs/35281171853)):
lint, unit-tests, integration-tests (20 real-Postgres repository-
lifecycle/generation tests passed — 16 from #166 plus 4 new for the
`/v1/repos/{repo_id}/generation` endpoint), bounded-memory. No target Linux
result is claimed.

## Evidence ledger

- `ingestion_service` unit suite: 314 passed (up from 310), 1 skipped, 72
  deselected — 4 new unit tests for the `/v1/repos/{repo_id}/generation`
  route's response-model wiring (mocked db_utils).
- `rag_orchestrator` full suite: 162 passed (up from 158), 1 skipped — 10
  new unit tests for `get_cached_graph`'s generation-keyed/bounded cache
  behavior, 4 new unit tests for `get_repo_generation`'s HTTP-failure
  degradation.
- Lint (`ruff`) clean on every touched file. Focused `pyright` on the
  touched core/API modules surfaces only the same pre-existing baseline
  import-resolution noise documented since R1/R2/R3 (no per-service venv in
  this shell) — no new type errors.
- `ingestion_service/tests/api/test_repo_generation_integration.py`
  (`integration`+`docker` marker, now CI-validated against real Postgres —
  see above) exercises the actual FastAPI route: unknown repo, ready repo,
  rebuild-in-progress (graph already replaced by the new attempt's
  `persist_graph`, not yet completed), and the specific
  re-ingest-under-same-`repo_id` scenario #168's acceptance criteria
  centers on.

## Acceptance coverage (against freshness.md's narrowed acceptance section)

- "Re-ingest a changed edge under the same repo_id; a warm worker must
  observe the new graph" — proven at two levels: the new endpoint reports
  the new `ingestion_id` after a second completed ingestion under the same
  `repo_id` (integration test, CI-validated), and `get_cached_graph`
  reloads when the resolved generation differs from its cached one (unit
  test, passing).
- "Delete/recreate cannot reuse old cached content" — unit test
  (`test_delete_and_recreate_cannot_reuse_old_cached_content`) covers the
  cache side (deleted repo -> `unknown` -> empty graph -> recreate ->
  new generation reloaded). Deletion itself is R3/#166's `delete_repo`,
  already CI-validated separately.
- "A generation change during retrieval does not combine snapshots" —
  `get_cached_graph` is called exactly once per `hybrid_retrieve` request
  (confirmed by reading `rag_orchestrator/src/core/service.py`), so
  resolving generation once per call structurally prevents mixing within
  one request. Not separately stress-tested with a concurrent mid-request
  rebuild, since the single-call-site property makes that race
  unreachable by construction, not something to additionally prove.
- "Cache eviction" — bounded LRU proven via
  `test_cache_is_bounded_across_repos`/`test_recently_used_repo_survives_eviction`.
- "Checking has-the-generation-changed does not require a full graph
  fetch" — the new endpoint is a single indexed DB lookup wrapped in HTTP,
  structurally distinct from `/v1/graph/repos/{repo_id}`'s full
  node/relationship export; `get_cached_graph`'s unit tests assert
  `load_graph_for_repo` is *not* called on a cache hit or on a
  not-yet-ready generation.
- "Pin runtime/source/ground truth independently in eval records" — out of
  this narrowed scope; moved to #181.

## Known limitations, disclosed rather than silently fixed

- No live two-service HTTP round-trip test exists (a real running
  `rag_orchestrator` process calling a real running `ingestion_service`
  process) — neither in this PR nor anywhere in CI today. Unit tests mock
  the HTTP seam on the orchestrator side; the new integration test
  exercises the endpoint against real Postgres on the ingestion side. Both
  together give real coverage of each side of the contract, not an
  end-to-end process test.
- Vector-store search still filters by `repo_id` only, not `ingestion_id` —
  a query's vector seeds and graph expansion are each internally
  consistent with *some* generation, but not formally proven to be the
  *same* generation in every race window between a rebuild's vector cleanup
  (R3, best-effort) and a concurrent query. Closing that fully is out of
  this ADR's scope (see ADR-051's non-goals).
- Ingestion source-revision provenance (#180) and evaluation
  three-revision provenance (#181) remain separate, unimplemented
  follow-ups; this PR does not touch either.

## Remaining gates

Final review and PR merge. Target Linux rollout evidence is recorded
separately under #171,
consistent with R1-R3's pattern.
