---
title: "Source Navigation API contract"
date: 2026-11-16
type: spec
status: accepted
summary: "Phase 6 / AG / AG0, #379: deterministic file discovery and bounded stored-source reads for the current completed generation. Deployment is operator-owned."
tags: [source-navigation, api, ag0, ingestion-service, issue-379]
related:
  - "[Issue #379](https://github.com/sankar-ramamoorthy/rag-foundry-universal/issues/379)"
  - "[ADR-055 supplement](/DOCS/adr/ADR-055-source-navigation-supplement.md)"
  - "[Canonical identity, ADR-031](/DOCS/adr/ADR-031-canonical-identity-model.md)"
  - "[Stored artifact text, ADR-041](/DOCS/adr/ADR-041-code-artifact-persistence-embedding-strategy.md)"
  - "[Read-only database assessment](/DOCS/test_results/2026-11-16-379-postgresql-source-ranges.md)"
---

# Source Navigation API

Tracking: Phase 6 / AG / AG0, #379. Preserve identity per ADR-031 and persistence
ownership per ADR-041. `ingestion_service` exposes two GET endpoints over its
existing source artifacts. The service's OpenAPI document includes the response
schemas and error envelope. No agent/model tools, symbol lookup, code search,
new source storage or changes to RAG answering are part of this API.

All operations require a repository UUID and the expected current completed
`generation_id` (ingestion UUID). This is a consistency fence, not a historical
snapshot selector. No checkout, filesystem, Git or vector chunks are consulted.
Deployment and already-ingested live HTTP verification remain operator-owned.

## Find files

`GET /v1/repos/{repo_id}/source/files`

| Query parameter | Meaning |
| --- | --- |
| `generation_id` | Required expected ready generation UUID |
| `pattern` | Case-sensitive path glob, default `**` |
| `limit` | Default 50, inclusive range 1–200 |
| `cursor` | Optional opaque continuation, at most 4,096 characters |

`*` matches within a path segment; `?` matches one nonseparator; a complete
`**` segment matches zero or more path segments. Other characters, including
brackets and SQL wildcard characters, are literal. For example `**/*.py` includes
root-level Python files; `*.py` includes only root-level files. Matching and
ordering use PostgreSQL `C` collation, retaining case and Unicode as stored.

Paths/patterns are at most 1,024 characters. Reject absolute/drive paths, NUL,
backslashes and empty/dot/traversal segments. No basename resolution is implied:
discover all candidates and pass one exact path to the read operation.

```json
{
  "repo_id": "...",
  "generation_id": "...",
  "commit_sha": null,
  "files": [
    {
      "path": "src/example.py",
      "canonical_id": "src/example.py",
      "document_id": "...",
      "doc_type": "python source",
      "source_status": "available"
    }
  ],
  "next_cursor": null
}
```

Discovery selects file identities, not function or synthetic nodes. Structural
records without source are included with `source_status=unavailable`; this is
not a complete listing of files on disk. Unsupported/legacy source types also
fail closed. `symbol_path IS NULL` is not a module classifier. Empty eligible
module text is available source; null text is unavailable. No source body is
selected by discovery. Supported readable types are the current Python,
TypeScript, JavaScript, Rust and Java source doc types.

Pagination is ordered by exact stored path and bound to repository, generation
and pattern. A cursor is a validated seek position, not an authorization token;
there is no new per-user authorization layer. Supplying it with different
filters is invalid. Reusing an obsolete generation returns a conflict rather
than another generation's next page. Empty results return `200` with `files=[]`.
An oversized response or unrepresentable bounded cursor returns `413`; reduce
page size or narrow the path pattern. No unusably oversized cursor is emitted.

## Read stored source

`GET /v1/repos/{repo_id}/source/read`

| Query parameter | Meaning |
| --- | --- |
| `generation_id` | Required expected ready generation UUID |
| `path` | Required exact repository-relative POSIX file path |
| `start_line` | Optional one-based start, inclusive |
| `end_line` | Optional inclusive end; requires `start_line` |

Omitting both bounds requests the complete file if it fits. A start without an
end requests at most 500 lines. An explicit interval must also contain at most
500 lines. End beyond EOF clamps to EOF; start beyond EOF fails explicitly.
Line boundaries use LF only. A terminal LF does not create a phantom extra
line; an empty source has no lines. Full empty reads use bounds 0/0; ranges
against empty source return `416`.

```json
{
  "repo_id": "...",
  "generation_id": "...",
  "commit_sha": null,
  "path": "src/example.py",
  "canonical_id": "src/example.py",
  "document_id": "...",
  "doc_type": "python source",
  "representation": "stored_source",
  "start_line": 101,
  "end_line": 200,
  "complete_file": false,
  "next_start_line": 201,
  "text": "...",
  "returned_text_sha256": "...",
  "text_sha256": null,
  "total_lines": null
}
```

The text preserves stored characters, indentation, blank lines and terminators.
It is decoded/normalized source as retained by ingestion, not a claim of Git
byte identity. `returned_text_sha256` always hashes returned UTF-8 text.
`text_sha256` is that hash only when the whole file is returned; it is null for
partial source. `total_lines` becomes known when the scan reaches EOF, otherwise
it is null. The original-file `content_hash` is not used as a stored-text hash.

`complete_file=true` means the returned interval covers the whole file, not just
that an explicit range was satisfied. `next_start_line` is null at EOF; otherwise
it indicates the following line, not a persisted offset cursor. Later requests
scan independently and may encounter the work cap even with small responses.

## Independent execution bounds

| Control | Limit |
| --- | ---: |
| Returned lines | 500 |
| Returned UTF-8 text | 128 KiB |
| Actual serialized JSON, including escapes and metadata | 256 KiB |
| Cumulative scanned UTF-8 text transferred from SQL | 1 MiB |
| Data queries per operation | 32 |
| Overall logical operation deadline | 5 seconds |

The query counter conservatively includes generation/identity queries as well
as substring windows; transaction setup and `SET LOCAL` timeout commands do not
retrieve data and are excluded. Thus there may be fewer than 32 source windows.
Windows contain at most 32,768 characters and shrink to the remaining byte
budget using the UTF-8 four-byte worst case before querying the database.

The deadline starts before validation/database acquisition and is checked during
scanning, hashing and serialization. Each data query receives only remaining
statement time. A separate four-connection read pool to the same database bounds
pool wait to one second and libpq connection establishment to two seconds;
acquisition time is charged to the operation. This does not change the general
ingestion pool. HTTP transport time and external scheduling are not real-time
guarantees. Synchronous DB work runs in FastAPI's thread pool.

No blanket 4 MiB file cap is imposed. A 5 MiB file can have readable early ranges
while late ranges fail with `SCAN_LIMIT_EXCEEDED`. No error response includes a
partial source body. The bounds do not guarantee constant PostgreSQL memory or
I/O: TOAST decompression can operate on prefixes or an entire value. These are
initial engineering policies, not measured throughput or tail-latency promises.

## Generation and lifecycle

Generation validation, file selection and source reads share a read-only
repeatable-read snapshot, materialized before the transaction ends. Unknown,
building and failed source states never fall back silently to another generation.
A ready owner can still be served while a new ingestion is being prepared;
once an incomplete replacement owns the rows there is no ready fallback.

An in-flight request opened before a committed rebuild/deletion may finish with
its original coherent snapshot. A subsequent request rejects that obsolete
generation or reports the repository unavailable. No transaction is held across
HTTP calls, and no historical-source availability is promised.

## Explicit failures

The existing error envelope is used at the top level:

```json
{
  "error_code": "SCAN_LIMIT_EXCEEDED",
  "message": "Source navigation work budget exceeded",
  "details": {"max_scan_bytes": 1048576, "max_queries": 32}
}
```

| HTTP | Stable code / condition |
| --- | --- |
| 400 | `INVALID_REQUEST`: missing/malformed UUID, path, glob, cursor, parameter type or page size |
| 404 | `REPOSITORY_NOT_FOUND`, `GENERATION_UNAVAILABLE`, or `FILE_NOT_FOUND` |
| 409 | `GENERATION_MISMATCH`; `AMBIGUOUS_PATH` if exact identity is inconsistent |
| 413 | `READ_TOO_LARGE`, `RESPONSE_TOO_LARGE`, or `SCAN_LIMIT_EXCEEDED` |
| 416 | `INVALID_LINE_RANGE`: nonpositive, reversed, empty or beyond EOF |
| 422 | `SOURCE_UNAVAILABLE`: a known file lacks a supported stored-source representation |
| 503 | `DEADLINE_EXCEEDED`, `INCONSISTENT_SOURCE`, or `SOURCE_UNAVAILABLE` on database/capacity failure |

No SQL text, source body, credentials or driver exceptions are exposed. Logs
contain operation counts, sizes and error codes. Requests are repository-scoped
but remain subject to existing deployment access controls; this API does not
create a user authentication/authorization system. Queries are parameterized;
glob text is escaped rather than treated as raw SQL or a caller-supplied regex.

## Validation and scope

Contract tests cover SQL source identity, repository isolation, empty/unsupported
files, exact LF ranges, Unicode and hashes, bound cursors, actual JSON escaping,
line/text limits, 5 MiB early/late reads, deadlines, read-only transactions, and
concurrent rebuild/deletion. Integration tests run against isolated local/CI
PostgreSQL, never the Linux production database. See the final #379 validation
record in project status for results and outstanding live verification.

#282 remains deferred batch/function-node access. Neither it nor any future
investigation engine is implemented by this API. The exploratory
[future-agent register](/DOCS/notes/brainstorm-20261116-future-agent-architecture.md)
does not authorize such work.
