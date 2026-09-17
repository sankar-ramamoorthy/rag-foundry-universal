# WP-R6: correct production healthchecks and expose runtime provenance

Tracking issue: [#169](https://github.com/sankar-ramamoorthy/rag-foundry-universal/issues/169)
Status: Implementation merged in PR #172; CI passed; Linux host validation pending.

Roadmap: Phase 4 production correctness, WP-R1 through WP-R8.

## Problem and evidence

Audit A8 identifies CMD-SHELL argument misuse and incorrect internal ports inherited by production Compose; HTTP health lacks build revision.

Source: DOCS/audit/2026-09-16-repository-architecture-audit.md at audited commit 308f0ac068fb0a8bdbb30ceba34cc6777abfb304.

## Proposed plan

Use executable argument-vector healthchecks with finite timeout and correct container-local ports; cover every application service. Expose configured image build revision through a read-only provenance endpoint, keeping image-label verification in release tooling.

## Acceptance and verification

Validate rendered base/prod Compose; execute probes against healthy and unavailable endpoints, checking nonzero failure. Test provenance defaults and built revision. Validate readiness on an isolated Linux stack; external HTTP 200 alone is not proof of Docker health state.

## Delivery tasks

- [x] Finalize issue-linked specification, plan, contracts, and acceptance tests.
- [x] Implement scoped fix on a dedicated branch; preserve service ownership and model provenance.
- [x] Run relevant local checks; record limitations honestly (Linux integration pending).
- [x] Update OKF knowledge-base links, current status, roadmap and evidence.
- [x] Commit, push, review CI, and merge the dedicated PR (#172).
- [x] Record deployment-specific gates separately from code completion.

## Implemented contract

All five app probes use exec-form `python3 -m shared.healthcheck` with a
2-second socket timeout inside Docker's 3-second timeout. API probes require
HTTP 200 and JSON `status=ok`; UI requires HTTP 200 with a nonempty body.
Container ports are 8000 for ingestion/LLM/RAG, 8002 for vector store, 7860
for Gradio. These are local HTTP liveness/startup gates, not proof of database,
model or corpus readiness. Functional lifecycle checks remain mandatory.

Four APIs expose read-only `GET /version`: service, git_sha, build_date,
release_version. Values come from APP_* environment baked from existing build
args; local defaults are unknown/unknown/dev. No Gradio version endpoint is
claimed. Compare all five running image IDs/OCI labels with approved SHA;
HTTP metadata alone is not image attestation and can be environment-overridden.

[Local evidence and Linux gates](/DOCS/test_results/2026-09-16-healthchecks-provenance-issue-169.md).
