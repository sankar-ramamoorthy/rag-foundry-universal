# WP-R3: make repository rebuild and deletion lifecycle consistent

Tracking issue: [#166](https://github.com/sankar-ramamoorthy/rag-foundry-universal/issues/166)
Status: Planned; no implementation or production validation implied.

Roadmap: Phase 4 production correctness, WP-R1 through WP-R8.

## Problem and evidence

Current graph rows are the only repository-to-ingestion mapping; retry after graph deletion cannot finish request cleanup, historical attempts disappear, and active ingestion can race deletion. Rebuild serving behavior is implicit. Covers audit A2/A3 and existing #144.

Source: DOCS/audit/2026-09-16-repository-architecture-audit.md at audited commit 308f0ac068fb0a8bdbb30ceba34cc6777abfb304.

## Proposed plan

Persist repository identity on ingestion attempts independently of nodes, backfill recoverable historical identities, serialize repository mutations across the full operation, atomically remove graph/request state after idempotent vector cleanup, and expose building/failed state without serving partial generations. Preserve canonical IDs under ADR-030/031. Explicit temporary unavailability during rebuild is the initial contract; zero-downtime staging is not silently assumed.

## Acceptance and verification

Fault-inject after vector cleanup and before/after graph commit; retry fully removes attempts. Test repeat ingestions, failure before graph creation, concurrent ingest/delete, and query rejection while rebuilding. Test PostgreSQL transactions and migration/backfill, not mocks alone.

## Delivery tasks

- [ ] Finalize issue-linked specification, plan, contracts, and acceptance tests.
- [ ] Implement scoped fix on a dedicated branch; preserve service ownership and model provenance.
- [ ] Run relevant unit/integration/evaluation checks; record limitations honestly.
- [ ] Update OKF knowledge-base links, current status, roadmap, ADRs where decisions change, and evidence.
- [ ] Commit, push, review CI, and merge the dedicated PR.
- [ ] Record deployment-specific gates separately from code completion.
