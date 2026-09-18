# WP-R7: prevent blocking ingestion, vector, and retrieval operations from stalling async services

Tracking issue: [#170](https://github.com/sankar-ramamoorthy/rag-foundry-universal/issues/170)
Status: Split into two PRs. PR 1 (delete_repo + vector-service routes,
[#185](https://github.com/sankar-ramamoorthy/rag-foundry-universal/pull/185))
CI-green, not yet merged. PR 2 (query embedding, optional reranker,
#168/WP-R5 graph-cache fetch) implemented on a dedicated branch, local
unit evidence only — see
[test results](/DOCS/test_results/2026-09-17-blocking-io-query-path-issue-170.md).
No production or Linux validation implied by either.

Roadmap: Phase 4 production correctness, WP-R1 through WP-R8.

## Problem and evidence

Audit A9 confirms synchronous DB/HTTP operations in async handlers and query embedding, graph loading, reranking on the event loop. Recorded delete freeze is consistent with this mechanism; its dominant duration is not yet profiled.

Source: DOCS/audit/2026-09-16-repository-architecture-audit.md at audited commit 308f0ac068fb0a8bdbb30ceba34cc6777abfb304.

## Proposed plan

Run synchronous route operations in the framework thread pool and offload synchronous substeps from async pipelines through bounded workers. Add finite embedding transport deadlines and admission limits; preserve model/fallback provenance. Profile delete stages separately; avoid unbounded executor submission.

## Acceptance and verification

Concurrency tests hold a fake slow database/provider/reranker call while an unrelated health/light request succeeds; saturation returns an explicit bounded response. Cover cancellation and exceptions. Run a controlled concurrency check on Linux and record delete stage timings without destructive load on user corpora.

## Delivery tasks

- [ ] Finalize issue-linked specification, plan, contracts, and acceptance tests.
- [ ] Implement scoped fix on a dedicated branch; preserve service ownership and model provenance.
- [ ] Run relevant unit/integration/evaluation checks; record limitations honestly.
- [ ] Update OKF knowledge-base links, current status, roadmap, ADRs where decisions change, and evidence.
- [ ] Commit, push, review CI, and merge the dedicated PR.
- [ ] Record deployment-specific gates separately from code completion.
