# CI-06 implementation plan — #337

Tracking: [#337](https://github.com/sankar-ramamoorthy/rag-foundry-universal/issues/337).
Phase 6 correctness follow-up to the
[November 10 audit](/DOCS/audit/2026-11-10-code-intelligence-architecture-audit.md)
(CI-06, linked to CI-03). Branch: `fix/337-ci06-embedding-input-coverage`.
The owner asked for investigation through PR preparation on 2026-11-10, without
deployment. Governing decision: proposed
[ADR-056](/DOCS/adr/ADR-056-embedding-input-contract.md). Investigation and
measurements: [CI-06 investigation](/DOCS/audit/2026-11-10-ci06-embedding-input-coverage-investigation.md)
and [verification](/DOCS/test_results/2026-11-10-ci06-embedding-input-coverage-verification.md).
Constitution Principles III and VIII apply (chunking change → evaluation
evidence); Principle V applies (vectors re-embedded deliberately via the reuse
gate, not silently mixed).

## Delivery and acceptance

- [x] Issue before implementation; coverage measurement before any chunker
  change; skeletal tests alongside the first spike.
- [x] Measure effective-input coverage and token fit on two development corpora
  (this repository at `75c3b4c`, LightRAG at the E1 pin `4d0afc1`). No held-out
  or production corpus.
- [x] Compare aligned contracts for discovery quality on sampled gap/control
  needle queries; exploratory run, then a larger confirmatory run on a new seed.
- [x] Shared contract module; chunker sizes every passage to it; the embedder
  never shortens input and records any unavoidable truncation per vector.
- [x] Reuse gate: chunking and embedding version strings change so a prior
  generation built under the legacy contract is fully re-embedded (CI-03 link);
  unchanged-contract reuse still works (real PostgreSQL test).
- [x] Unit, integration and lint/type checks; failures compared with `main`.
- [x] Evidence, status, log and PR description recorded.
- [x] Published [PR #339](https://github.com/sankar-ramamoorthy/rag-foundry-universal/pull/339);
  remote CI passed on the implementation head ([run](https://github.com/sankar-ramamoorthy/rag-foundry-universal/actions/runs/42956421223)).
- [x] Independent review (R1–R5) verified and resolved: no passage truncation
  (split on model rejection), generation-fenced reuse with real PostgreSQL
  regression tests, serving-model token-fit validation, pre-registered bounded
  delivery evaluation (all criteria passed), identity/rollout limits in ADR-056.
- [x] Owner decision (2026-11-11): clean rebuild of existing indexes at
  deployment; keep the generation fence; no historical compatibility.
- [ ] Owner review and merge. Deployment and rebuild are operator-owned.

Handoff for resuming: [CI-06 handoff note](/DOCS/notes/2026-11-10-ci06-embedding-input-contract-handoff.md).

## Out of scope

- Extractor behavior in the reuse identity and immutable model digests: the rest
  of CI-03 (#313).
- Uploaded Markdown/Docling section ingestion, broken independently since #81:
  #338.
- Document-upload chunk granularity: kept as-is apart from the per-unit size cap,
  because no document-RAG evaluation was run for this change.
