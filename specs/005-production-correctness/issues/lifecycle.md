# WP-R3: make repository rebuild and deletion lifecycle consistent

Tracking issue: [#166](https://github.com/sankar-ramamoorthy/rag-foundry-universal/issues/166)
Original delivery: merged via PR #178; ADR-050 records acceptance and real-PostgreSQL
CI evidence. Linux rollout evidence remains a separate gate. See
[ADR-050](/DOCS/adr/ADR-050-repository-lifecycle-consistency.md) (accepted)
and [test-results evidence](/DOCS/test_results/2026-09-17-repository-lifecycle-issue-166.md).

Roadmap: Phase 4 production correctness, WP-R1 through WP-R8.

## Problem and evidence

Current graph rows are the only repository-to-ingestion mapping; retry after graph deletion cannot finish request cleanup, historical attempts disappear, and active ingestion can race deletion. Rebuild serving behavior is implicit. Covers audit A2/A3 and existing #144.

Source: DOCS/audit/2026-09-16-repository-architecture-audit.md at audited commit 308f0ac068fb0a8bdbb30ceba34cc6777abfb304.

## Proposed plan

Persist repository identity on ingestion attempts independently of nodes, backfill recoverable historical identities, serialize repository mutations across the full operation, atomically remove graph/request state after idempotent vector cleanup, and expose building/failed state without serving partial generations. Preserve canonical IDs under ADR-030/031. Explicit temporary unavailability during rebuild is the initial contract; zero-downtime staging is not silently assumed.

## Acceptance and verification

Fault-inject after vector cleanup and before/after graph commit; retry fully removes attempts. Test repeat ingestions, failure before graph creation, concurrent ingest/delete, and query rejection while rebuilding. Test PostgreSQL transactions and migration/backfill, not mocks alone.

## CI-01 clarification (accepted 2026-11-10; not implemented)

The [graph snapshot contract](../contracts/repository-graph-snapshot.md) and
amended ADR-050 require one read snapshot for actual graph ownership, completed
status, expected-generation validation, nodes and relationships, with the actual
`ingestion_id` in the ready export. Preferred design is one export-scoped,
read-only PostgreSQL repeatable-read transaction; source review supports its
feasibility with existing atomic replacement and later completion commits.
Share the reader session across helpers and materialize fields before closing it.

A different ready generation conflicts with an expectation (409); building,
failed and unknown remain explicit unavailable outcomes. A completed attempt
without graph rows does not establish a ready zero-node snapshot. Zero edges
in a ready graph are valid. A snapshot established before rebuild/delete can
finish reading A, without promising a new request can retrieve historical A.
Zero-downtime staging remains outside scope.

Acceptance adds real PostgreSQL barrier-controlled rebuild/delete interleavings
at owner/node/edge boundaries, surviving IDs with changed edge metadata, completion
timing, rollback and reader cleanup. Verify effective isolation and no settings
leak into pooled writer connections. The contract's full acceptance matrix is
required before claiming this follow-up closed. Documentation acceptance does
not authorize application changes or retroactively extend original test evidence.

## Original delivery tasks

- [x] Finalize issue-linked specification, plan, contracts, and acceptance
  tests (ADR-050; this file).
- [x] Implement scoped fix on a dedicated branch (`fix/166-repo-lifecycle-
  consistency`); preserve service ownership and model provenance.
  - `repo_id` persisted on `ingestion_requests` (migration + backfill),
    computed deterministically at HTTP accept time.
  - Repo-scope advisory lock serializes ingest vs. delete of the same
    `repo_id`; delete additionally rejects outright while an ingestion is
    active for that `repo_id`.
  - `list_ingestion_ids_for_repo` now primarily sources `repo_id`, with a
    `document_nodes` fallback — a retry after graph deletion (or an
    attempt that never wrote a node) still completes.
  - `resolve_current_generation`/`generation_status` gate graph reads on
    the owning ingestion's actual status (`ready`/`building`/`failed`/
    `unknown`), matching `persist_graph`'s real atomic-replace behavior
    rather than assuming a prior generation stays visible during rebuild.
  - Post-completion cleanup of superseded generations' vectors/requests
    (best-effort, non-fatal on failure).
- [x] Run relevant unit/integration checks; record limitations honestly —
  see evidence doc. All four CI checks pass at head `ec5ada9` (run
  35276251850), including the new real-PostgreSQL repository-lifecycle
  suite (16 tests) — the integration-tests job's file allowlist had to be
  extended to actually run it and the pre-existing
  `test_db_utils_repo_delete.py`, neither of which CI executed before.
- [x] Update OKF knowledge-base links, current status, roadmap, ADR-050,
  and evidence doc.
- [x] Commit, push, review CI (green), PR #178 open — merge pending final
  review/authorization.
- [ ] Record deployment-specific gates (Linux/#171) separately from code
  completion.
