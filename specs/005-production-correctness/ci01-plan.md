# CI-01 implementation plan — #335

Tracking: [#335](https://github.com/sankar-ramamoorthy/rag-foundry-universal/issues/335).
Phase 6 follow-up to #166/#168. Branch: `fix/ci01-generation-bound-graph-export`.
Owner approved implementation on 2026-11-10 after approving the
[snapshot contract](./contracts/repository-graph-snapshot.md).
Governing decisions: amended ADR-050/051; preserve ADR-030/031 and service
ownership under the constitution. No retrieval-policy or schema change.

## Delivery and acceptance

- [x] Issue and approved contract before implementation; skeletal PostgreSQL
  route/snapshot tests created alongside the first code spike.
- [x] Producer: one read-only repeatable-read export transaction, materialized
  envelope, expected-generation fence and coherent cheap lookup.
- [x] Consumer: validate identity/status/content before graph construction/cache;
  preserve bounded LRU and whole-request fences; direct structural identity.
- [x] Real PostgreSQL deterministic interleavings for owner/node/edge reads,
  rebuild/delete/completion, rollback and request cleanup; pooled settings,
  deadlines, exceptions and abandoned readers.
- [x] Route/client/loader/cache composition, unavailable/legacy/protocol outcomes,
  warm/forced/concurrent loads and structural consumers; existing fence regression.
- [x] Relevant service tests, Ruff, Pyright and CI integration selection. Full
  repository Pyright remains red; focused checks/baseline comparison and all
  commands/results are in the [evidence](/DOCS/test_results/2026-11-10-ci01-graph-snapshot-verification.md).
- [x] Record commands/results/limits in a test-result and current status; prepare
  the [issue-linked PR description](./ci01-pr-description.md). Actual PostgreSQL
  verification is complete locally.
- [ ] Publish branch/PR, review remote CI and merge. Automatic approval review
  requires explicit owner authorization for the remote publication; implementation
  approval alone was rejected for that action. No production deployment is included.

Export deadline starts at 60 seconds, configurable using
`GRAPH_EXPORT_TIMEOUT_SECONDS`. Each SQL phase receives the remaining statement
and idle-transaction timeout; materialization checks the same monotonic deadline.
HTTP client read timeout starts at 70 seconds. These bound reader work rather
than truncate data; measurements and limitations belong in the evidence report.
Production deployment is outside this work.
