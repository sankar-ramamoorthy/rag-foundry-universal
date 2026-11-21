# Implementation plan: verified per-window source ranges (#416)

Plan for `specs/015-per-window-source-ranges/spec.md`. **A plan only: no code is
authorized until the owner approves it.** Governing issue:
[#416](https://github.com/sankar-ramamoorthy/rag-foundry-universal/issues/416).
Roadmap phase: Phase 6. Test-guided: each work package starts with its failing
tests.

## Scope held tight

Attach a verified `start_line`/`end_line` (or an explicit reason) to existing
passage windows. Passage text, boundaries, embeddings, ordinals and
`ChunkerFactory.VERSION` do not change, so nothing is re-embedded. No migration.
Not in scope: #417 (same-line prefix), Markdown, retrieval, any search-based
location.

## Facts the plan rests on (observed in the code)

- `shared/chunkers/text.py::line_windows` builds windows from an ordered
  `pieces` list (`splitlines(keepends=True)` plus sub-line splits) and already
  holds each window's first piece index (`start`), so a character offset is
  `sum(len(p) for p in pieces[:start])`. `TextChunker.chunk` (strategy
  `line_window`) wraps each window as `Chunk(content, chunk_id, metadata={})`.
- `ingestion_service/src/api/v1/codebase_ingest.py::_chunk_and_buffer_node`
  chunks `node.text`, then tags every chunk; #412 added `_passage_span`, which
  gives a range only for one chunk. Page rows already carry `start_line` and
  `end_line` of the artifact (#412).
- `HttpVectorStore._build_record` copies the whole `chunk.metadata` into the
  vector row's `source_metadata`; `vector_chunks` has `chunk_index`,
  `chunk_text`, `document_id`, `ingestion_id`.
- Reuse: `_embed_repo_artifacts` sends reused artifacts to
  `HttpVectorStore.retag_ingestion_id`, which calls the vector store's
  `POST /v1/vectors/retag` (`PgVectorStore.retag_ingestion_id`): one
  `psycopg.connect` block, so one transaction per request, fenced by
  `expected_ingestion_id`, with an existing `jsonb_set` patch for provenance.
- Overflow (`IngestionPipeline._embed_fitted`) may further split a window into
  pieces at embed time and shifts later `chunk_index` values (CI-06).

## Work packages (dependency order; one PR each, each tracked by #416)

### WP1. Chunker reports offsets (`shared/`, ingestion tests)

- Add `line_window_offsets(text, max_chars, overlap, max_tokens) ->
  list[tuple[str, int]]` implementing the existing algorithm, returning each
  window with its character offset. Reimplement `line_windows` as
  `[w for w, _ in line_window_offsets(...)]`.
- `TextChunker.chunk(strategy="line_window")` records the offset on the chunk as
  a transient key (`window_offset`) that ingestion removes before persisting, so
  no new stored metadata beyond `start_line`/`end_line`/`range_reason`.
- Offsets are character offsets (not bytes) into the exact input string.
- **Tests first:** property test that `line_windows` output equals the offset
  variant's texts and that each `text[offset:offset+len(w)] == w`, over generated
  inputs (overlap on/off, long lines, CRLF, multi-byte, empty, single line);
  a pin test that `ChunkerFactory.VERSION` and window counts for fixtures are
  unchanged.

### WP2. Window ranges at embed time (ingestion service)

- `source_span.window_range(artifact_text, artifact_start, offset, window)`:
  offset check (`artifact_text[offset:offset+len(window)] == window`), then LF
  mapping with a prefix count of `\n` (computed once per artifact, O(n), not per
  window), returning `(start, end)` or a reason from the spec's table.
- `_chunk_and_buffer_node` replaces `_passage_span` for the multi-window case:
  every window is tagged from its offset; `window_offset` is popped before
  buffering; an unverified artifact range yields
  `artifact range not verified`; a chunker without offsets yields
  `window offset not reported`.
- `_embed_fitted` overflow pieces: keep `piece_ranges`, now subdividing the
  window's range. Add the consistency test (pieces lie inside the window range).
- **Tests first:** the spec's table: overlapping windows, repeated text (same
  block three times, each window its own range), long line, first/last/single
  window, corrupted offset, unverified artifact, CRLF and lone CR, multi-byte,
  overflow pieces. Each resolving case is checked by a consumer-style read-back
  against the stored text (the existing `resolves` helper pattern).
- **Merge gate:** WP2 is useful alone: new and changed files get ranges. Reused
  files still need WP3 and WP4.

### WP3. Digest-guarded range patch in the vector store

- Extend `VectorRetagRequest` with an optional
  `source_ranges_by_document_id: {document_id: [{chunk_index, text_sha256,
  start_line, end_line, range_reason}]}` (backward compatible: absent means
  today's behavior).
- In `PgVectorStore.retag_ingestion_id`, inside the same transaction as the
  retag: for each entry, update only rows where `document_id`, `chunk_index`
  and `ingestion_id = expected_ingestion_id` match **and**
  `encode(sha256(convert_to(chunk_text,'UTF8')),'hex') = text_sha256`. Set only
  `source_metadata.start_line`, `end_line`, `range_reason` via `jsonb_set`
  (remove the keys not applicable); never touch `vector`, `chunk_text`,
  `chunk_index`, `chunk_id`, `provider` or other keys.
- Result gains `ranges_patched` and `ranges_skipped` (with the skipped
  `(document_id, chunk_index)` pairs, bounded in size). A skipped row is still
  retagged (it is the same artifact) but its metadata is unchanged.
- **Atomicity (required):** a single transaction covers the retag and the
  patches. Any exception rolls back everything for that request; no row is left
  moved with a stale or partial range. Skipped-by-digest rows are the only
  permitted exception and are unchanged and reported.
- The ingestion client sends reused documents in bounded batches (existing
  batching). Atomicity is per request; a batch that fails leaves its documents on
  the prior generation, which the existing "re-embed what was not retagged"
  step already handles. State this in the PR.
- **Tests first** (against the real Postgres used by the vector store tests):
  success; digest mismatch (row untouched, counted); stale generation (whole
  request rejected, nothing changes); unknown document; **failure injection
  after some rows are processed** with an assertion that every row's
  `ingestion_id` and `source_metadata` equal their prior state; scope test that
  only the three keys differ after success; byte-for-byte preservation of
  `vector` and `chunk_text`.

### WP4. Ingestion computes ranges for reused artifacts

- In the reuse branch of `_embed_repo_artifacts`, for each reused node compute
  windows with the same chunker and config (guaranteed unchanged by
  `config_matches`), derive ranges with WP2's function and send them in the
  retag request with each window's `text_sha256`.
- Overflow caveat: if the original embed split a window into pieces, the stored
  passages will not match the recomputed window digest, so the patch skips them
  and they keep their current reason. This is safe by construction and measured.
- Log and report `ranges_patched` and `ranges_skipped` in the ingestion progress.
- **Tests first:** an incremental ingest of an unchanged file gains ranges with
  no embedding calls (assert zero embed calls and unchanged chunk counts); a
  skipped (mismatched) row is reported; a stale prior generation rejects.
- Deploy order: vector store first (new optional field is ignored by an old
  ingestion), then ingestion. No migration.

### WP5. Orchestrator and docs

- No orchestrator code change expected: citations already carry the persisted
  range and reason. Add a test that each reason in the spec's table passes
  through unchanged, and that a malformed range is still never repaired.
- Update spec 014 and `DOCS/status.md`; retire the
  `artifact split into several passages` reason in the docs for new generations.

### WP6. Live audit (not committed code)

- A personal read-only audit (kept untracked, like `db_inspect.py`): read the
  passage list by SELECT, then for a random sample of at least 1,000 ranged
  passages plus every non-null non-legacy reason, call
  `GET /v1/repos/{id}/source/read` at the same generation and check the lines
  contain the window text exactly (first-line prefix and last-line suffix
  allowed). Record results in `DOCS/test_results/` using the baseline note's
  format; raw captures go in `_raw/` with an index entry.
- The audit procedure and acceptance thresholds are committed in the results
  note; the script is not.

## Measurement sequence (against the recorded baseline)

1. Deploy WP3 then WP1 and WP2 (vector store first). Full rebuild of Mealie at
   `1624c22` with `force_full_rebuild`.
2. Measure yield: passages with a range over passages whose artifact range is
   verified (target at least 85%; the baseline was 25.8% of all passages).
3. Audit (WP6): zero incorrect ranges.
4. Deploy WP4. Incremental ingest with no file change: confirm reused passages
   gain ranges, zero embedding calls, text and vectors unchanged.
5. Re-measure `/v1/rag` citation range yield on the same questions.

## Risks and how the plan handles them

| Risk | Handling |
| --- | --- |
| Offsets drift from the chunker's real cut | Offsets come from the chunker itself and are verified against the artifact text; a mismatch is null, never a wrong range |
| `splitlines` splits on more separators than LF | Lines are counted from `\n` in the text; pieces are never used to count lines |
| Quadratic cost of counting newlines per window | One prefix count per artifact, O(n) |
| Retag payload size for large reused repositories | Existing bounded batches; ranges payload is small integers and a digest per passage |
| Overflow pieces misalign stored `chunk_index` with recomputed windows | Digest guard skips them; they stay explicit nulls and are counted |
| Partial generation transition | One transaction per request, failure-injection test, rejection leaves rows unchanged |
| Vector store and ingestion deployed out of order | New field optional; deploy vector store first |

## PR slicing and gates

1. WP1 + WP2 (chunker offsets and ingestion ranges). 2. WP3 (vector store
patch). 3. WP4 (+ WP5 docs). Each PR: unit tests green, required CI green on the
current head (CLAUDE.md merge gate), integration test for any column-set or
contract the change touches, ruff and pyright error set unchanged, status
update. Implementation does not start until this plan is approved.

## Open points for the owner

- Confirm three PRs in the order above, or fold WP3 and WP4 together.
- Confirm that the live audit script stays untracked (it uses the personal
  read-only database access) with the procedure recorded in the results note.
