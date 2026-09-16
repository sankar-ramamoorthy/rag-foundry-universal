# WP-R6: correct production healthchecks and expose runtime provenance

Tracking issue: [#169](https://github.com/sankar-ramamoorthy/rag-foundry-universal/issues/169)
Status: Planned; no implementation or production validation implied.

Roadmap: Phase 4 production correctness, WP-R1 through WP-R8.

## Problem and evidence

Audit A8 identifies CMD-SHELL argument misuse and incorrect internal ports inherited by production Compose; HTTP health lacks build revision.

Source: DOCS/audit/2026-09-16-repository-architecture-audit.md at audited commit 308f0ac068fb0a8bdbb30ceba34cc6777abfb304.

## Proposed plan

Use executable argument-vector healthchecks with finite timeout and correct container-local ports; cover every application service. Expose configured image build revision through a read-only provenance endpoint, keeping image-label verification in release tooling.

## Acceptance and verification

Validate rendered base/prod Compose; execute probes against healthy and unavailable endpoints, checking nonzero failure. Test provenance defaults and built revision. Validate readiness on an isolated Linux stack; external HTTP 200 alone is not proof of Docker health state.

## Delivery tasks

- [ ] Finalize issue-linked specification, plan, contracts, and acceptance tests.
- [ ] Implement scoped fix on a dedicated branch; preserve service ownership and model provenance.
- [ ] Run relevant unit/integration/evaluation checks; record limitations honestly.
- [ ] Update OKF knowledge-base links, current status, roadmap, ADRs where decisions change, and evidence.
- [ ] Commit, push, review CI, and merge the dedicated PR.
- [ ] Record deployment-specific gates separately from code completion.
