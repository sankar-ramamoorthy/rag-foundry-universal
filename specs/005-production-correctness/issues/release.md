# WP-R8: verify the current Linux release across the complete corpus lifecycle

Tracking issue: [#171](https://github.com/sankar-ramamoorthy/rag-foundry-universal/issues/171)
Status: Planned; no implementation or production validation implied.

Roadmap: Phase 4 production correctness, WP-R1 through WP-R8.

## Problem and evidence

A successful September 12 release exists, but current-release fresh ingest/query/delete/redeploy and revision/source provenance remain unverified. Production is Linux/GTX 1080 Ti over Tailscale with no SSH.

Source: DOCS/audit/2026-09-16-repository-architecture-audit.md at audited commit 308f0ac068fb0a8bdbb30ceba34cc6777abfb304.

## Proposed plan

Extend release tooling with repeatable lifecycle verification on an explicitly isolated smoke corpus, revision/image/mount and migration checks, health/UI checks, deletion retry verification, and a release record. Integrate #160 memory benchmark and #161 recovery evidence; retain hardware/runtime/source/model identity and rollback instructions.

## Acceptance and verification

All preceding red-star fixes merged with required CI. Operator supplies container-level evidence where no remote command channel exists. Pinned fixture ingest completes with full vectors, query uses that generation, delete removes smoke data, redeploy preserves expected state, startup recovery works, healthchecks reflect failure correctly. Never close on scripts or HTTP reachability alone.

## Delivery tasks

- [ ] Finalize issue-linked specification, plan, contracts, and acceptance tests.
- [ ] Implement scoped fix on a dedicated branch; preserve service ownership and model provenance.
- [ ] Run relevant unit/integration/evaluation checks; record limitations honestly.
- [ ] Update OKF knowledge-base links, current status, roadmap, ADRs where decisions change, and evidence.
- [ ] Commit, push, review CI, and merge the dedicated PR.
- [ ] Record deployment-specific gates separately from code completion.
