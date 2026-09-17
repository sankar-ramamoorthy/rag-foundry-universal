---
title: "WP-R3 repository rebuild/delete lifecycle verification"
date: 2026-09-17
type: test-results
status: partial
tags: [ingestion, lifecycle, repository, postgres, acceptance]
related:
  - "[ADR-050](/DOCS/adr/ADR-050-repository-lifecycle-consistency.md)"
  - "[R3 acceptance and tasks](/specs/005-production-correctness/issues/lifecycle.md)"
  - "[Programme handoff](/specs/005-production-correctness/HANDOFF.md)"
---

# WP-R3 verification — #166

## Scope and current result

R3 is implemented on branch `fix/166-repo-lifecycle-consistency` (PR #178),
not yet merged or deployed. All four CI checks pass at head `ec5ada9`
(run [35276251850](https://github.com/sankar-ramamoorthy/rag-foundry-universal/actions/runs/35276251850)):
lint, unit-tests, integration-tests (including the new real-PostgreSQL
repository-lifecycle suite — 16 tests passed), bounded-memory. The
integration-tests job's file allowlist did not include
`test_repo_lifecycle.py` or the pre-existing `test_db_utils_repo_delete.py`
until this PR's second commit wired them in; the first commit's "passing CI"
was silently not exercising either suite. No target Linux result is claimed.

## Evidence ledger

- Local ingestion unit suite: 310 passed, 1 skipped, 68 deselected (up from
  307/1/58 pre-R3 — 3 new unit tests for `ingest_repo`'s `repo_id` threading
  plus repo-lock/active-ingestion route tests). Repository lint (`ruff`)
  passes on every touched file. Focused `pyright` on the touched core/API
  modules surfaces only the pre-existing baseline import-resolution noise
  documented since R1/R2 (no ingestion_service-local venv in this shell) and
  one new, now-fixed `str | None` narrowing in `ingest_repo`.
- `tests/api/test_repos_delete.py` (unit, mocked DB): extended with
  `TestDeleteRepoLock` covering repo-busy-returns-409 and active-ingestion-
  blocks-delete-and-releases-lock; existing ordering/idempotency tests
  updated for the new pre-checks and still pass unchanged in intent.
- `tests/api/test_ingest_repo_id.py` (new, unit): `repo_id` is computed
  deterministically at accept time (same URL -> same `repo_id` across calls)
  and threaded into `submit_ingestion`; `RepositoryBusy` maps to a retryable
  409.
- `tests/core/test_repo_lifecycle.py` (new, `integration`+`docker`, now
  wired into CI's `integration-tests` job and passing against real
  Postgres): repo_id survives graph
  deletion and enumerates an attempt that never wrote a node; generation
  resolution reports `unknown`/`building`/`ready`/`failed` correctly,
  including the specific case that motivated the redesign — a rebuild whose
  `persist_graph` has already replaced `document_nodes` but has not reached
  `completed` must not be served as `ready`; a completed generation survives
  a later failed attempt that never touched `document_nodes`; the repo-scope
  lock blocks ingest against delete in both directions; superseded-
  generation identification excludes only the current id.

## Acceptance coverage (against lifecycle.md's acceptance section)

- "Retry fully removes attempts" — `repo_id` on `ingestion_requests` makes
  this possible even after graph rows are gone; CI-validated.
- "Concurrent ingest/delete" — repo-scope advisory lock plus an explicit
  active-ingestion check on delete; CI-validated.
- "Query rejection while rebuilding" — `generation_status`/
  `resolve_current_generation` return `building` and empty nodes/
  relationships rather than serving a not-yet-complete rebuild; this is
  enforced at the `ingestion_service` graph-read layer
  (`get_full_graph_for_repo`, `get_document_nodes_by_canonical_ids`).
  Consuming that signal in `rag_orchestrator`'s cache (`codebase_utils.
  get_cached_graph`) is explicitly **not** done here — that is WP-R5/#168's
  generation-consistent-caching scope, not R3's.
- "Test PostgreSQL transactions and migration/backfill, not mocks alone" —
  migration `20260917_add_repo_id_to_ingestion_requests` backfills from
  `document_nodes` and runs for real in CI (`Apply migrations` step); the
  backfill UPDATE itself is not separately exercised against seeded
  pre-migration legacy rows (only against the fresh, always-empty CI
  database), so its SQL is CI-applied but its actual backfill behavior on
  historical data is unverified. This remains an honest gap.

## Known limitations, disclosed rather than silently fixed

- Superseded-generation vector cleanup after a successful rebuild is
  best-effort: if the vector-store call fails, the new generation is still
  considered complete and stale vectors remain until a manual `DELETE
  /v1/repos/{repo_id}` or retry. This degrades recall (dead document_id
  references silently dropped during graph expansion) but does not corrupt
  the new generation's own data.
- No zero-downtime staged publication: `persist_graph`'s existing atomic
  replace already makes a repository's graph momentarily reflect an
  in-progress rebuild before embeddings finish, which is why
  `generation_status` must report `building` (not "still serving the old
  generation") during that window. This is the explicitly allowed initial
  contract per the programme spec, not an oversight.
- `rag_orchestrator`'s in-memory graph cache
  (`retrieval/codebase_utils.py::get_cached_graph`) does not yet consult
  `generation_status`; a cached graph fetched before a rebuild can still be
  served stale until evicted/reloaded. Tracked under #168, not this issue.

## Remaining gates

Final review and PR merge. Target Linux rollout evidence is recorded
separately under #171, consistent with R1/R2's pattern. The migration
backfill's behavior against real historical (pre-#166) data is unverified —
noted above, not blocking merge since new rows are always populated
correctly and the fallback path covers any row the backfill missed.
