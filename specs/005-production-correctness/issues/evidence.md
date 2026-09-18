# WP-R4: preserve retrieved passages, chunk identity, and final-context provenance

Tracking issue: [#167](https://github.com/sankar-ramamoorthy/rag-foundry-universal/issues/167)
Status: Implementation complete and code-reviewed clean against ADR-052 on
`fix/wp-r4-evidence-delivery` (commit `cbb84d7`) — see
[mechanics verification](/DOCS/test_results/2026-09-17-wp-r4-evidence-delivery.md).
The mandatory quality-evaluation gate (frozen 8-question set vs. legacy
runtime, plus a partial clean-context control) completed 2026-09-18
against the Tailscale production Ollama (local CPU Ollama had been the
blocker in four earlier attempts) — see
[quality evaluation](/DOCS/test_results/2026-09-18-wp-r4-quality-evaluation.md).
**Net positive result, no blocking findings**: WP-R4 answered more
frozen questions correctly than legacy (5/8 vs. 3/8), one pre-existing
retrieval gap unrelated to WP-R4 was confirmed (not a regression), and
the one case where WP-R4 scored worse than legacy was root-caused to the
new byte-based budget correctly enforcing itself where the old one never
did (documented, intended trade-off, not a defect). Production/deployment
validation remains separately gated (#171) and is not claimed here.

Roadmap: Phase 4 production correctness, WP-R1 through WP-R8.

## Problem and evidence

Audit A4/A5/A6 confirms arbitrary limited document fetching, overwritten chunk indices, pre-budget sources, and simple-RAG expansion omitted during assembly. Related #91, #141, #145, #149 and #156 remain separately measurable quality cases.

Source: DOCS/audit/2026-09-16-repository-architecture-audit.md at audited commit 308f0ac068fb0a8bdbb30ceba34cc6777abfb304.

## Proposed plan

Preserve stored indices, select query-relevant passages within discovered and seeded artifacts using bounded requests, include document expansions, derive sources and manifest from the exact final prompt selection, separate rerank drops, enforce a documented conservative token budget with prompt headroom, and explicitly sort relaxed vector-search candidates. Address same-relation cap loss with measured deterministic candidate selection; no new model/reranker default.

## Acceptance and verification

Payload-level tests for long-function tail evidence, seed supplementation, same-relation overload, simple-document expansion, oversized context, and source-manifest equality. Run uncontaminated pinned question sets, stage attribution, matched-budget controls, and clean/noisy-context checks under the quality methodology before claiming quality completion.

## Delivery tasks

- [x] Finalize issue-linked specification, plan, contracts, and acceptance tests.
- [x] Implement scoped fix on a dedicated branch; preserve service ownership and model provenance.
- [x] Run relevant unit/integration/evaluation checks; record limitations honestly.
- [x] Update OKF knowledge-base links, current status, roadmap, ADRs where decisions change, and evidence.
- [ ] Commit, push, review CI, and merge the dedicated PR.
- [ ] Record deployment-specific gates separately from code completion (separate #171 gate; not this issue's job).

## Implemented contract under verification

See [ADR-052](/DOCS/adr/ADR-052-evidence-delivery-context-selection.md) for
passage API ordering/scoping, stored ordinal versus fetch position, final
context assembly and conservative budget semantics. Local mechanics evidence
and remaining acceptance are in the [verification record](/DOCS/test_results/2026-09-17-wp-r4-evidence-delivery.md).
