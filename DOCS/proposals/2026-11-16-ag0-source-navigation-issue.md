---
title: "Source Navigation API: AG0 issue draft"
date: 2026-11-16
type: proposal
status: obsolete
summary: "Historical issue-preparation record for #379. The measured limits were accepted and implementation authorized; the accepted source-navigation API spec is the current contract."
tags: [source-navigation, ag0, api, ingestion-service]
related:
  - "[Current API contract](/DOCS/architecture/source-navigation-api.md)"
  - "[Source Navigation API #379](https://github.com/sankar-ramamoorthy/rag-foundry-universal/issues/379)"
  - "[ADR-055 supplement](/DOCS/adr/ADR-055-source-navigation-supplement.md)"
  - "[Existing batch node-text issue #282](https://github.com/sankar-ramamoorthy/rag-foundry-universal/issues/282)"
  - "[Exact-file retrieval diagnostic #361](https://github.com/sankar-ramamoorthy/rag-foundry-universal/issues/361)"
---

# Source Navigation API — Generation-Aware Access to Persisted Source Code

**Historical preparation record.** The owner subsequently accepted the range
assessment and authorized implementation with the scan/query/deadline limits.
Use the [accepted API contract](/DOCS/architecture/source-navigation-api.md) for
current behavior; the filed preparation body below is retained as history.

Tracking issue: [#379](https://github.com/sankar-ramamoorthy/rag-foundry-universal/issues/379).
This document preserves the filed issue contract. The initial sandbox
credential failure was resolved by using the owner's verified keyring login
outside the sandbox. The [#282 reconciliation](https://github.com/sankar-ramamoorthy/rag-foundry-universal/issues/282#issuecomment-6937842241)
is posted. Endpoint implementation awaits review of the remaining measured
database-read design gate.

The [read-only PostgreSQL assessment](/DOCS/test_results/2026-11-16-379-postgresql-source-ranges.md)
now records measurements at available sizes and recommends a scan-work budget
as an explicit contract adjustment for review. The issue body below remains
the filed preparation contract; above-4-MiB validation remains unfulfilled.

## Decision and governance
Roadmap: Phase 6 / workstream AG / AG0 (Agent-ready evidence contracts). No GitHub milestone, per constitution Principle VI and the owner's approval on 2026-11-16. Preparation is approved; return the issue and contract for review before implementing endpoints.

Expose existing persisted source through ingestion_service. Initial delivery is only find_files and read_source for the current completed generation. No agent/controller, model tools, find_symbols, search_code, new service, new source archive, schema expansion, or database. No RAG answering-path change or deployment.

## Motivation and verified boundaries
The owner's codebase_utils.py function-inventory query received unrelated script/test evidence and an abstention. This proves inadequate supplied evidence, not that the whole file exists in the deployed database. No deployed database claim is made.

Code assessment at 87379aa: DocumentNode is unique on (repo_id, canonical_id); persistence updates source and ingestion_id in place and deletes absent artifacts. Superseded ingestion records are cleaned up. Historical source is not a supported capability. Reuse read_snapshot and snapshot-local generation resolution from db_utils, not separate resolve-then-fetch sessions. A ready owner may still be served while another ingestion is being prepared; once its rows are replaced by an incomplete generation there is no safe ready fallback.

## Relationship to ADR-055, #282 and #361
Keep #282 open, deferred, as the distinct canonical-ID batch/function-node capability for the E1 experiment. Do not implement its POST /nodes/text in AG0, close it, or claim AG0 satisfies function-node access. AG0 reads file modules only. When #282 proceeds, it must reuse the generation/source-selection primitives, stored-text/hash semantics and limits policy established here; its batch envelope and E1 gate remain separate. Record this explicitly in a supplement to ADR-055 and link the supplement from #282. #361 remains a separate diagnostic of end-to-end RAG selection and completeness, not automatically fixed by these APIs.

## Deterministic readable-source predicate
Within the requested repo and current ready ingestion, a readable file requires canonical_id = relative_path, an exact source doc_type allowlist emitted by current code extractors (python source, typescript source, javascript source, rust source, java source), and text IS NOT NULL. symbol_path IS NULL is insufficient and must not drive this decision. The empty string is a valid empty source module; nonempty text is not required. Structural inventory records use file/manifest doc_types and must be reported as source unavailable, never confused with empty code. Unknown/legacy doc_types fail closed; no heuristic reconstruction or schema repair in this issue. Tests cover symbols whose persisted symbol_path is NULL, imports/synthetic nodes, empty modules, structural files, and null-text source records.

## API and response contract
- GET /v1/repos/{repo_id}/source/files?generation_id=...&pattern=...&limit=...&cursor=...
- GET /v1/repos/{repo_id}/source/read?generation_id=...&path=...&start_line=...&end_line=...
Every operation requires an expected generation_id. It is a fence on the current completed ingestion, not historical selection.

find_files returns {repo_id, generation_id, commit_sha, files:[{path, canonical_id, document_id, doc_type, source_status}], next_cursor}. Enumerate exact file-identity rows, including structural-only records with source_status=unavailable. No source text in discovery. Case-sensitive glob syntax: * matches within one segment, ? matches one nonseparator, ** as a segment matches zero or more segments. Stable path ordering uses a documented bytewise database collation. Default pattern **; default page 50, max 200. Cursor binds repo, generation, pattern, and last path; validate it and recheck generation on every page. Limit path/pattern to 1024 characters and cursor to 4096; bound pattern execution; do not materialize the entire repository to filter it.

read_source returns {repo_id, generation_id, commit_sha, path, canonical_id, document_id, doc_type, representation:stored_source, start_line, end_line, complete_file, next_start_line, text, returned_text_sha256, text_sha256, total_lines}. returned_text_sha256 always hashes the returned text encoded as UTF-8. text_sha256 is the whole stored-source hash and is required for complete-file responses; it and total_lines may be null on bounded reads rather than forcing a whole-file scan. Document these nullable fields. Do not substitute DocumentNode.content_hash, which hashes original file bytes. Stored text has already been UTF-8 decoded and newline-normalized at ingestion: never claim Git-byte identity.

Line numbers are one-based, inclusive; split on stored LF only and preserve exact characters and line terminators. Empty text has zero lines; a terminal LF adds no phantom line. Omitting both bounds requests the complete file if it fits. start_line alone requests at most 500 lines from that point (clamp only at EOF and report actual bounds); end_line requires start_line. end_line beyond EOF clamps to EOF; start past EOF or reversed/nonpositive ranges are explicit failures. An empty complete-file response uses start_line=0,end_line=0 and complete_file=true. Exact path only: no basename fallback. Discovery returns all ambiguous basename candidates; a duplicate persisted exact identity fails closed rather than choosing a row.

## Bounded reads and the withdrawn 4 MiB cap
Do not introduce the previously proposed blanket 4 MiB artifact rejection. PostgreSQL supports substring(text FROM start FOR count), so a range path can return bounded character windows without sending the whole value to the application. This does not prove constant database memory/I/O: TOAST decompression, line-offset discovery and late-line scans can still be expensive. Reference: https://www.postgresql.org/docs/current/functions-string.html

Require a measured PostgreSQL range-query design before endpoint implementation: bounded character-window reads/scanning or an equivalent bounded projection, preserving UTF-8 characters and LF boundaries. Never split the entire value into an application/SQL line array. Initially target 32 Ki-character database windows, max 500 returned lines, max 128 KiB UTF-8 text, max 256 KiB actual serialized response (escaping and metadata included), and 5 s request/database deadline. Verify applicability on the repository's PostgreSQL version. Over-limit responses return 413 without partial success; timeouts return 503. Full reads can preflight octet_length before selecting text. A small range from a source larger than 4 MiB must work within measured limits. If measurements require a temporary artifact cap or different strategy, document evidence and obtain a contract adjustment rather than silently adding it. A giant individual line may be unreadable under the response cap and must fail explicitly.

## Isolation, lifecycle and security
All row queries constrain repo_id and snapshot-resolved ingestion_id. Validate generation, select identity and read windows in one read-only repeatable-read transaction with a deadline; reuse existing snapshot primitives. Do not keep a transaction across requests. An in-flight request may complete coherently against the snapshot opened before replacement/deletion; the next request must reject the old generation. No promise of global latest-at-response-time semantics.

Validate UUIDs and exact relative POSIX paths; reject absolute/drive/UNC paths, backslashes, NULs, dot/traversal segments and malformed cursors; preserve case and Unicode without normalization. Queries are parameterized; glob input is not raw SQL/regex. Never access Git, host files or remote URLs. Use synchronous handlers/thread-pool execution for synchronous DB work. Log counts/timing/sizes only, never source bodies. Preserve existing deployment access controls; repository scoping is not new per-user authorization.

Errors use a documented envelope with error_code/message/details and repo-scoped expected/current generation/status where safe: 400 invalid input/cursor; 404 unknown/deleted repository, no ready generation (GENERATION_UNAVAILABLE with status), or FILE_NOT_FOUND; 409 GENERATION_MISMATCH when a ready generation differs; 413 size limit; 416 invalid/out-of-file line interval; 422 SOURCE_UNAVAILABLE for known structural/unsupported/null-text records; 503 timeout/inconsistent ownership. Empty discovery returns 200. This retains ADR-055's no-completed-generation 404 convention. Do not expose another repo's generation existence. Prefer existing error-envelope conventions over a parallel format.

## Acceptance tests and independent verification
- [ ] HTTP schema/error examples, defaults, glob semantics, nullable metadata and limits documented; skeletal tests precede or accompany implementation.
- [ ] Two repos sharing paths and canonical IDs never leak content or cursor results.
- [ ] Readable-source predicate covers empty source, structural-only files, null source, symbols with NULL symbol_path, synthetic nodes and legacy types.
- [ ] Stable discovery ordering/pagination; generation/filter-bound cursor; no missing or duplicate files; literal wildcard-like characters and Unicode tested.
- [ ] Exact preservation for LF, normalized ingestion CRLF, Unicode, indentation, blank lines, empty files and missing/final LF. Concatenating accepted ranges reproduces stored source; hash semantics checked separately from raw-file hash.
- [ ] Real PostgreSQL tests race reads/pages with rebuild, failure, completion and deletion; no mixed generation or stale-current fallback; old generation rejected on subsequent reads.
- [ ] Greater-than-4-MiB module with a small early and late range works within measured limits. Giant-line, 128-KiB boundary and JSON-escaping expansion fail explicitly. Assert bounded transfer/application allocation and record DB plan/time/limitations, including compressed/TOAST values.
- [ ] Another HTTP route stays responsive during expensive reads; timeout yields explicit 503; no unbounded query/whole-line-array materialization.
- [ ] Run ingestion unit tests and appropriate PostgreSQL integration tests. No claims of performance or live success without measurements.
- [ ] After operator deployment, read-only verification on an already-ingested Python file: pin runtime/source revisions and repo/generation, retrieve all ranges, verify completeness, parse returned source locally to inventory all functions (including async/nested definitions), and compare with an independently pinned source reference. codebase_utils.py is the motivating development case, not a quality generalization claim. If stored source is absent, record it; no automatic ingestion/deployment.
- [ ] Record the approved architectural supplement in Foundry; update docs index/log/status and #282 cross-reference. No agent/model tool or RAG behavior changes.

## Remaining pre-implementation gate
The measured SQL/windowing strategy and safe execution budgets remain unverified. Preparation may include a local isolated database experiment, but this issue does not claim one has run. Return this issue and any evidence-based contract adjustment to the owner before implementing endpoints.
