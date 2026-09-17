# WP-R3: make repository rebuild and deletion lifecycle consistent

Tracking issue: [#166](https://github.com/sankar-ramamoorthy/rag-foundry-universal/issues/166)
Status: Implemented on a dedicated branch, unit-tested locally; real
PostgreSQL/CI evidence and merge pending. See
[ADR-050](/DOCS/adr/ADR-050-repository-lifecycle-consistency.md) (proposed)
and [test-results evidence](/DOCS/test_results/2026-09-17-repository-lifecycle-issue-166.md).

Roadmap: Phase 4 production correctness, WP-R1 through WP-R8.

## Problem and evidence

Current graph rows are the only repository-to-ingestion mapping; retry after graph deletion cannot finish request cleanup, historical attempts disappear, and active ingestion can race deletion. Rebuild serving behavior is implicit. Covers audit A2/A3 and existing #144.

Source: DOCS/audit/2026-09-16-repository-architecture-audit.md at audited commit 308f0ac068fb0a8bdbb30ceba34cc6777abfb304.

## Proposed plan

Persist repository identity on ingestion attempts independently of nodes, backfill recoverable historical identities, serialize repository mutations across the full operation, atomically remove graph/request state after idempotent vector cleanup, and expose building/failed state without serving partial generations. Preserve canonical IDs under ADR-030/031. Explicit temporary unavailability during rebuild is the initial contract; zero-downtime staging is not silently assumed.

## Acceptance and verification

Fault-inject after vector cleanup and before/after graph commit; retry fully removes attempts. Test repeat ingestions, failure before graph creation, concurrent ingest/delete, and query rejection while rebuilding. Test PostgreSQL transactions and migration/backfill, not mocks alone.

## Delivery tasks

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
- [x] Run relevant unit/integration checks locally; record limitations
  honestly — see evidence doc. Real-Postgres/CI run pending (this is a
  local-only checkpoint at branch creation; run in CI before merge).
- [x] Update OKF knowledge-base links, current status, roadmap, ADR-050,
  and evidence doc.
- [ ] Commit, push, review CI, and merge the dedicated PR.
- [ ] Record deployment-specific gates (Linux/#171) separately from code
  completion.
