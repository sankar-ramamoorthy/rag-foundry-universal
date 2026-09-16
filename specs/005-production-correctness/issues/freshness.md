# WP-R5: bind ingestion snapshots and graph caches to corpus generation

Tracking issue: [#168](https://github.com/sankar-ramamoorthy/rag-foundry-universal/issues/168)
Status: Planned; no implementation or production validation implied.

Roadmap: Phase 4 production correctness, WP-R1 through WP-R8.

## Problem and evidence

Audit A7 confirms indefinitely cached graphs keyed only by repo_id, no source revision pin/recording, and evaluation source/runtime drift.

Source: DOCS/audit/2026-09-16-repository-architecture-audit.md at audited commit 308f0ac068fb0a8bdbb30ceba34cc6777abfb304.

## Proposed plan

Accept and verify an explicit Git ref, record resolved source SHA and configuration fingerprint; propagate ingestion generation through repository resolution, graph loading and query provenance; bound graph cache and reload on generation change; detect generation changes across a query rather than combine snapshots. Honor ADR-031 canonical identity without appending generation to canonical IDs.

## Acceptance and verification

Re-ingest a changed edge under the same repo ID; a warm worker must observe the new graph. Delete/recreate cannot reuse old cached content. Verify pinned checkout, invalid refs, dirty local source disclosure, cache eviction, and a generation change during retrieval. Pin runtime/source/ground truth independently in eval records.

## Delivery tasks

- [ ] Finalize issue-linked specification, plan, contracts, and acceptance tests.
- [ ] Implement scoped fix on a dedicated branch; preserve service ownership and model provenance.
- [ ] Run relevant unit/integration/evaluation checks; record limitations honestly.
- [ ] Update OKF knowledge-base links, current status, roadmap, ADRs where decisions change, and evidence.
- [ ] Commit, push, review CI, and merge the dedicated PR.
- [ ] Record deployment-specific gates separately from code completion.
