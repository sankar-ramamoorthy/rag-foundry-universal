---
title: "WP-R1 bounded ingestion — implementation and verification evidence"
date: 2026-09-17
type: test-result
status: partial
tags: [ingestion, memory, production, issue-160]
related:
  - "[Memory specification](/specs/004-bounded-ingestion-memory/spec.md)"
  - "[Memory design review](/DOCS/audit/2026-09-16-bounded-ingestion-memory-design-review.md)"
  - "[Production correctness roadmap](/DOCS/audit/07-Roadmap.md)"
  - "[Execution handoff](/specs/005-production-correctness/HANDOFF.md)"
---

# Scope and implementation status

Issue #160, draft [PR #175](https://github.com/sankar-ramamoorthy/rag-foundry-universal/pull/175).
Implementation exists on its branch, not yet merged or deployed. The worker
now pages persisted artifacts, bounds both chunk count and UTF-8 bytes, carries
explicit per-document ordinals, and releases the graph-build frame before
embedding. No chunk/model change or resumable ingestion claim is made.

Initial limits: page 32 nodes, artifact 1,048,576 UTF-8 bytes, buffer 128 chunks
and 262,144 UTF-8 bytes. PostgreSQL preflight rejects oversized artifacts before
text projection. Every page binds repository and ingestion attempt. Existing
full-operation mutation coordination is still insufficient: #161/#166 remain
production prerequisites, not properties supplied by paging.

## Verified results

- Local Windows locked root Python 3.12: ingestion unit suite **288 passed**,
  1 skipped, 44 deselected at worker integration checkpoint a28b421.
- 48 focused batch/streaming tests pass. Real chunker produces 143 chunks from
  128,000 characters; buffer sizes 1/7/128 preserve text/ordinals. Tests also
  cover metadata, deterministic stub vectors, Unicode byte bounds, oversized
  chunks, invalid input cardinality/indices, provider timeout, empty input,
  missing generation, and prior acknowledgements after write failure.
- Weak-reference tests check that graph/builder references leave scope before
  embedding and predecessor pages are not held while fetching successors.
  These are lifetime tests, **not RSS measurements**.
- Linux CI at 9edf84b, run
  [35219308277](https://github.com/sankar-ramamoorthy/rag-foundry-universal/actions/runs/35219308277):
  lint/unit/integration jobs pass. **9 paging/progress/HTTP integration tests**
  pass against migrated PostgreSQL+pgvector; existing 5 atomic graph and 12 ANN
  tests also pass.
- A real, separately launched vector-service process receives HTTP writes.
  Fresh PostgreSQL sessions observe each acknowledged batch. Normalized stored
  output (canonical ID, ordinal, exact text, metadata, provider and 1024-dimensional
  deterministic vector) matches across buffer sizes 1/7/128: 144 vectors from
  one short artifact and the 143-chunk artifact.
- Injecting failure after two committed seven-vector HTTP batches leaves 14
  vectors and a durable failed request with acknowledged count 14. This is
  **exception-path durability**, not kill/recovery or checkpoint/resume proof.
- Fresh sessions and the actual status handler observe progress updates;
  terminal completed/failed stages preserve counters and failure details.

First paging CI found an invalid test UUID (`absent`), corrected before the
passing run. Unit coverage alone would not have detected this database mismatch.
Root Ruff passes. New buffer modules pass focused pyright; broader ORM modules
retain typing errors and root tooling lacks GitPython, so no full type-clean
claim is made.

## Commands and reproduction

From ingestion_service with the locked root interpreter:

```text
../.venv/Scripts/python.exe -m pytest -m unit -q
../.venv/bin/python -m pytest tests/codebase/test_artifact_paging.py -q -s
```

The second command runs in Linux CI with DATABASE_URL selecting the isolated
`ingestion_test` database and migrations applied. The HTTP fixture explicitly
rejects databases whose name does not end in `_test`. It launches only a local
test vector service, and only deletes vectors belonging to its generated
fixture attempt. No production corpus or model provider is accessed.

## Outstanding gates — not waived

- Inspect actual keyset EXPLAIN (planner probe added after the passing run),
  then decide on an index from evidence.
- Stage-aware Linux fresh-process N/4N and large-artifact RSS harness, raw
  samples and preregistered SC-002 acceptance; distinguish graph/full-run peak.
- Full normalized graph/topology parity beyond existing golden tests.
- Hard-kill durability/recovery under #161 and full-operation coordination
  under #166; existing exception test is insufficient for those requirements.
- Pinned DocsGPT source SHA, runtime SHA, model and declared cgroup memory
  ceiling; full vector coverage and successful completion under SC-001.
- Target Linux GTX1080Ti lifecycle/redeployment evidence under #171. Tailscale
  HTTP access without SSH does not establish Docker/cgroup provenance.

Keep #160 open and PR draft while implementation/validation work remains.
