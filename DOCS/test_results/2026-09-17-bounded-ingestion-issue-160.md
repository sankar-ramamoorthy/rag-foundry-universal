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

## Linux synthetic calibration (not acceptance)

Run 35220047904, PR head d0b6603, measured synthetic merge SHA
f3230ab9ae7af0d4843d57fded833f473513f7ae, Python 3.12.3 on Linux.
Real generated Python graph builder, SQL pages and HTTP vector persistence;
deterministic 1024-D Python-float embedder. Runtime defaults unchanged.

| Fixture | Nodes/vectors | Embedding RSS baseline → peak | Increment |
| --- | --- | --- | --- |
| N: 512 files | 1,024 / 1,024 | 174,084,096 → 182,075,392 bytes | 7,991,296 bytes |
| 4N: 2,048 files | 4,096 / 4,096 | 184,107,008 → 188,891,136 bytes | 4,784,128 bytes |
| Large: 4 files, 128k payload | 8 / 1,144 | 170,426,368 → 180,322,304 bytes | 9,895,936 bytes |

The unchanged SC-002 comparison passes (4N increment below 45,541,376-byte
threshold). Graph/build peak increases with input size; retained allocator pages
help explain why 4N's embedding increment is smaller. Do not infer zero graph
cost or constant whole-process memory. All observed page/artifact/buffer limits
hold. Cgroup mount-root files were unavailable, recorded as null, not a known
memory ceiling. No GPU/provider memory was measured.

Raw archived evidence: [comparison](./data/issue-160-calibration-35220047904/comparison.json),
[N](./data/issue-160-calibration-35220047904/N.jsonl),
[4N](./data/issue-160-calibration-35220047904/4N.jsonl),
[large](./data/issue-160-calibration-35220047904/large.jsonl).
These include raw timestamps, RSS/HWM, stage markers, limits, counts and runtime
identity. Separate acceptance measurement still required after calibration.

**The overall CI run failed:** ingestion's 11 tests passed, but after benchmark
cleanup the existing ANN suite returned zero results in three tests despite
its seeded rows. [#176 plan](/specs/005-production-correctness/issues/post-delete-ann.md)
tracks this new lifecycle/retrieval evidence. A test-only vacuum diagnostic is
added without suppressing the original failure. A repeat run 35220317090
passed the original ANN tests, so the conditional vacuum diagnostic did not run:
the symptom is intermittent, not proven vacuum-responsive. Exact-search,
pgvector-version and controlled-churn evidence remain #176 work. Subsequent
memory acceptance uses its own CI job/database for reproducible isolation;
this is explicitly **not** a production recall fix.

## Separate synthetic acceptance

After inspecting calibration, run 35220643252 used the same defaults, fixture
sizes and criterion, with phase explicitly set to `acceptance` and its own
test database. Measured synthetic merge SHA
12447724d8758cde05affb6748afa3c2d75b5622 (PR head c264325).

| Fixture | Embedding increment | Full-process VmHWM |
| --- | --- | --- |
| N | 2,088,960 bytes | 262,983,680 bytes |
| 4N | 4,788,224 bytes | 188,796,928 bytes |
| Large | 9,863,168 bytes | 180,305,920 bytes |

4N increment is below the unchanged 36,687,872-byte threshold. All live limits
and persisted counts passed. N's startup baseline was higher than the other
fresh processes; retain that variation rather than substituting a shared
baseline. Whole-process VmHWM is read independently from raw samples, not
mislabelled as an embedding-stage peak. It includes imports and fixture setup.

[Acceptance comparison](./data/issue-160-acceptance-35220643252/comparison.json),
[N raw](./data/issue-160-acceptance-35220643252/N.jsonl),
[4N raw](./data/issue-160-acceptance-35220643252/4N.jsonl),
[large raw](./data/issue-160-acceptance-35220643252/large.jsonl).
SC-002 synthetic acceptance is satisfied; SC-001 DocsGPT is **not**.

Follow-up fb33c4b, CI run 35220823709, passed independent actual graph rebuilds
at buffer sizes 1/7/128. Canonical node sets and CALL/other edge endpoints match
the graph-builder reference, and normalized graph rows and persisted vector
contents match across rebuilds, ignoring generated internal UUIDs. All four CI
jobs passed, including independent memory acceptance.

## Outstanding gates — not waived

- Paging EXPLAIN at f9868f1, CI run 35219461132: 4,000 fixture nodes,
  late keyset page, 32 returned rows, existing document_nodes_pkey Index Scan,
  0 rows removed by filter, 38 shared-hit blocks, 0.036 ms execution. Ten
  integration tests passed. **No new index justified by this fixture**; it is
  not a selective multi-repository workload, so revisit indexing if larger
  mixed-corpus measurement shows excessive filtered scans. Raw plan is in
  that run's bounded-artifact-paging step (`PAGING_EXPLAIN`).
- Hard-kill durability/recovery under #161 and full-operation coordination
  under #166; existing exception test is insufficient for those requirements.
- Pinned DocsGPT source SHA, runtime SHA, model and declared cgroup memory
  ceiling; full vector coverage and successful completion under SC-001.
- Target Linux GTX1080Ti lifecycle/redeployment evidence under #171. Tailscale
  HTTP access without SSH does not establish Docker/cgroup provenance.

Keep #160 open for production gates. Implementation PR may merge after final
green checks, with the unexecuted deployment dependencies explicitly retained.
