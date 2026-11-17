---
title: "#379 Source Navigation API implementation and verification"
date: 2026-11-16
type: test-result
status: complete
summary: "File discovery and stored-source reads implemented with accepted bounds. Local PostgreSQL tests and local HTTP reads against the unchanged Linux database verified; no Linux deployment."
tags: [source-navigation, api, ag0, tests, issue-379]
related:
  - "[Issue #379](https://github.com/sankar-ramamoorthy/rag-foundry-universal/issues/379)"
  - "[API contract](/DOCS/architecture/source-navigation-api.md)"
  - "[ADR-055 supplement](/DOCS/adr/ADR-055-source-navigation-supplement.md)"
  - "[Pre-implementation assessment](/DOCS/test_results/2026-11-16-379-postgresql-source-ranges.md)"
  - "[Raw evidence index](/DOCS/test_results/raw-index.json)"
---

# #379 implementation and verification

The owner accepted the PostgreSQL assessment, authorized the adjusted limits,
and requested implementation, documentation, commit and merge through a PR.
Deployment to Linux was explicitly excluded. Scope: Phase 6 / AG / AG0,
`find_files` and `read_source` only; #282 remains deferred.

## Result

`ingestion_service` now implements:

- `GET /v1/repos/{repo_id}/source/files`
- `GET /v1/repos/{repo_id}/source/read`

The [API contract](/DOCS/architecture/source-navigation-api.md) records schemas,
defaults, source eligibility, exact LF-based line semantics, hashes, pagination,
errors and lifecycle behavior. All source data comes from existing DocumentNode
rows in a single read-only repeatable-read snapshot per operation. No schema,
agent, model tools, source archive, search subsystem or RAG answering policy was
added. The existing database pool's behavior was preserved; a small read pool to
the same database bounds source-reader connection wait and establishment.

Accepted limits are implemented separately: 500 lines, 128 KiB returned UTF-8
text, 256 KiB actual JSON including escaping, 1 MiB cumulative source-scan
transfer, 32 data queries and a five-second logical-operation deadline. Remaining
time reaches the database's statement timeout; application scanning, hashing and
serialization are checked against the same deadline. UTF-8 windows shrink before
SQL to respect remaining transfer budget. Over-budget operations return explicit
errors without partial source or false absence.

## Local isolated PostgreSQL acceptance

Started a dedicated local Docker `pgvector/pgvector:pg15` container and applied
the existing migrations to `ingestion_test`. The test guard refuses integration
fixture writes outside a local `*_test` database. No production fixtures were
created; the existing Linux database was not used for integration/concurrency
writes. Tests generate unique repository identities and clean their own rows.

**41 focused tests passed** (25 unit and 16 PostgreSQL/HTTP integration cases),
including:

- Identical paths in separate repositories; exact module identity rather than
  null symbol metadata; structural, unknown, null-text and empty-source records.
- Stable C-collation pagination, case and Unicode preservation, literal regex/SQL
  metacharacters, zero-segment `**` matching, and generation/filter-bound cursors.
- Exact reconstructed ranges, LF-only boundaries, blank lines, missing/final LF,
  stored CRLF, Unicode separators treated as characters, UTF-8 hashes and EOF.
- A **5,242,944-byte** stored source (more than 5 MiB): its early range succeeds;
  its late range returns `413 SCAN_LIMIT_EXCEEDED`, not partial text or `404`.
- 500/501-line limits; exactly 128 KiB source success; an oversized multibyte
  line fails; JSON control-character escaping can independently exceed 256 KiB.
- Incomplete/failed replacement never falls back to the previous source; unknown
  versus accepted-but-unready repositories have explicit error codes.
- A separate committed writer rebuilds/deletes while a reader is paused after
  generation selection or after a source window. The in-flight read remains old
  and coherent; the subsequent request conflicts or reports absence.
- A real `pg_sleep` read is interrupted by its remaining SQL timeout while an
  unrelated async ping responds. Application/serialization deadline tests fail
  explicitly. Read transactions report read-only repeatable-read and reject SQL
  UPDATE with PostgreSQL code `25006`.

The CI workflow now explicitly runs the new PostgreSQL integration module.

Additional local verification:

| Check | Result |
| --- | --- |
| Root `tests/` | 286 passed, including the nine benchmark diagnostic tests |
| Ingestion `-m unit` | 508 passed, 4 existing skips, 143 deselected |
| Existing graph-snapshot, generation and atomic-persistence integration modules | 39 passed |
| Ruff across the repository | Passed |
| Scoped Pyright for new implementation, tests and diagnostic | Passed |
| Repository-wide Pyright | 417 diagnostics; unrelated/global baseline is not clean |
| Staged-file pre-commit hooks | Ruff, address scan, whitespace and EOF checks passed; global Pyright excluded after recording its full-run failure |

Counts overlap: focused unit cases also appear in the ingestion unit suite.
The repository-wide Pyright result is explicitly recorded rather than represented
as a passing whole-repository type check. It includes existing audit/raw scripts,
multi-service import resolution and existing service/type problems. No unrelated
type-checking configuration or source files were changed to hide these errors.
The all-files hook run also found legacy whitespace/EOF problems. Its automatic
edits to 61 unrelated files were verified as whitespace-only, backed up and
restored from the pre-hook index; frozen evaluation files were not reformatted.
Only the new issue draft's EOF fix was retained. No global formatter cleanup is
included in this change.

## Independent local HTTP verification against Linux stored evidence

Ran a **local in-process HTTP TestClient** with only the new source router,
configured to read the existing Linux PostgreSQL database. It did not start the
ingestion application's lifespan/recovery worker, deploy a Linux service or
invoke ingestion. The source connection reported `transaction_read_only=on`.

Both file discovery (`**/codebase_utils.py`) and complete-file reading returned
`200` for:

- Repository: `f7641840-ba13-5f9d-9ae6-87e1f924709d`.
- Generation: `8cbedbb9-9ad6-4c63-83f7-2b7d7659f7e5`.
- Source revision: `9f039c43604b2e96a6f96351e00afa178c9c81f8`.
- Path: `rag_orchestrator/src/retrieval/codebase_utils.py`.
- Complete response: **10,479 UTF-8 bytes, 274 lines, 13 functions**.
- Text hash: `f1a037bab5dee68db183b8c9b64ea6e434194ed13a5b6e79719b0f2bc8877bf1`,
  matching the previously verified stored text and decoded Git object.

The complete returned source was parsed locally with Python AST for its function
inventory; this does not add a symbol endpoint to Foundry. Source bodies and
connection credentials are absent from the retained capture. The
[raw index](/DOCS/test_results/raw-index.json) registers
`2026-11-16-379-local-api-linux-db.json` with the endpoint/core implementation
hashes, identities, results and function names. The new router ran locally over
the existing data; this is **not production HTTP endpoint verification**.

## Contract clarifications and remaining limits

- The 32-query counter includes generation and file metadata reads, making it
  more conservative than 32 source windows. Transaction-control/timeout SETs
  do not retrieve data and are not counted as data queries.
- A four-connection read pool with one-second pool wait and two-second libpq
  connection timeout prevents the general pool's 30-second queue from consuming
  the source deadline. It accesses the same existing database and is not new
  storage. HTTP transport/external scheduling are not real-time guarantees.
- Discovery whose actual JSON or opaque cursor exceeds its cap fails explicitly
  rather than emitting a truncated page or a cursor rejected on the next call.
- Whole-file hash and total-line metadata remain explicitly nullable for partial
  reads. `next_start_line` does not promise an indexed or constant-cost next read.
- The 5 MiB fixture verifies functional safety under the scan cap; it is not a
  throughput, backend peak-memory or cold-cache capacity benchmark. The earlier
  production corpus genuinely lacked sources above 4 MiB.
- Existing RAG answers will not automatically use these endpoints. #282 and
  future agent architecture remain separate. No Linux deployment or production
  endpoint rollout is performed by this change.

README claims/examples were checked against route registration, defaults,
response behavior, service ports and these tests. License declarations remain
Apache-2.0. Changes are delivered through the dedicated #379 branch and PR;
CI/merge provenance is recorded on that PR rather than invented in this report.
