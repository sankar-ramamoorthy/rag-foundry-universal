# Tasks: bounded ingestion memory

Tracking issue: #160
Roadmap: WP-R1
Spec: [spec.md](./spec.md)
Plan: [plan.md](./plan.md)

## Setup and tests

- [x] T001 Validated page/count/byte/artifact settings and env/Compose examples.
- [ ] T002 Skeletal 143-chunk-node, cross-buffer ordinal, byte/Unicode,
      normalized parity, whitespace/empty and oversized rejection tests.
- [ ] T003 Real PostgreSQL generation-scoped page/count/disappearance tests,
      explicitly included in CI integration selection.
- [ ] T004 Extract existing language-suffix helper without behavior change.

## Implementation

- [ ] T005 Narrow keyset pages with repo_id+ingestion_id, byte preflight,
      consistent inclusion and completion count checks.
- [ ] T006 Graph helper scope ends before embedding; prove no full references.
- [x] T007 Optional explicit chunk_indices through pipeline/persistence,
      with cardinality and ordinal validation.
- [ ] T008 Count+byte bounded chunk buffers; persist before successor.
- [ ] T009 Remove canonical-map use from this embedding path.
- [x] T010 Finite embedding transport deadline and failure propagation.
- [ ] T011 Pre-allocation stages, fresh-JSON progress, 0/0 case and maxima.
- [ ] T012 Verify WP-R2/R3 admission/mutation exclusion before deployment.

## Validation and delivery

- [ ] T013 Normalized parity at 1/7/128; text/metadata/ordinals/canonical edges.
- [ ] T014 DB interruption tests: prior writes survive; no false resume claim.
- [ ] T015 Stage-aware RSS N/4N and large-artifact harness; record SC-002.
- [ ] T016 Pinned DocsGPT under declared/recorded ceiling; full coverage/SC-001.
- [ ] T017 Relevant service tests, lint, type checks and required CI.
- [ ] T018 Update KB/current status/roadmap/evidence; distinguish implemented
      from production-validated and retain historical audit.
- [ ] T019 Commit/push dedicated implementation PR; merge green checks.
      Keep #160 open while mandatory memory evidence is missing.

T002 before/alongside code. T007 precedes split-artifact persistence.
T006 ships with T008. T003/T014 require Postgres. T015/T016 require isolated
Linux measurement. Next-session state:
[HANDOFF](../005-production-correctness/HANDOFF.md).
