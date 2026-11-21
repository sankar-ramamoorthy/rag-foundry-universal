# Verified per-window source ranges for split passages

[Phase 6 specification for issue #416](https://github.com/sankar-ramamoorthy/rag-foundry-universal/issues/416).
Follows `specs/014-persisted-source-spans/spec.md` (#412) and the citation
contract in `specs/012-structured-citations/spec.md` (#407). **Specification
only. No implementation is authorized by this document.**

Read against ADR-039/041 (artifact is the embedding unit; text lives on the
node), ADR-056 (a stored passage is the exact embedding input), ADR-030/031
(identity and rebuild determinism are unchanged) and the #196 incremental reuse
rules.

## Problem

Code artifacts are chunked into overlapping exact line windows. #412 gives a
range only to artifacts stored as one passage, so on the Mealie baseline only
4,556 of 17,676 passages (25.8%) carry a range and 11,063 (62.6%) are null with
`artifact split into several passages`, although those artifacts' own ranges are
verified. A citation to such a passage cannot be resolved to its lines.

Contract (owner, 2026-11-21): a range that is advertised resolves to the exact
source content it represents; if it cannot be established it is null with an
explicit reason, never guessed.

## Principle: attach, do not change

The location is metadata about an existing window. This work must not change
any passage's text, its boundaries, its embedding, the chunk order or ordinals,
or the chunking config version (`ChunkerFactory.VERSION`, currently
`budgeted-v2`). A test pins this (see Verification).

## Design

### 1. The chunker reports where it cut (no searching)

`line_windows` builds windows from an ordered list of pieces (whole lines, or
sub-line splits for a line over budget) and already knows each window's first
piece. Add a variant that returns, for each window, its character offset in the
input text. The existing `line_windows` becomes a thin wrapper that drops the
offsets, so its output is identical by construction; a property test compares
the two over generated inputs.

Because the offset comes from the chunker, repeated text and overlapping
windows are **not** ambiguous: a window is identified by position, never by
searching for its content. Searching is explicitly not used.

### 2. Verify, then map to lines

At ingestion, where the artifact text and its verified range (#412) are both in
hand, for each window:

1. **Offset check:** `artifact_text[offset : offset + len(window)] == window`.
   Any mismatch, no offset reported, or an unverified artifact range gives a
   null range with a reason (below).
2. **Map to lines** under the source read API's convention (LF only; the
   chunker splits on more separators than LF, so lines are counted from `\n` in
   the text, never from the chunker's pieces):
   `start = artifact_start + count("\n", 0, offset)` and
   `end = artifact_start + count("\n", 0, offset + len(window) - 1)`.
3. A window that begins or ends inside a long line names the line(s) containing
   it, the same whole-line rule as #412. A window that only overlaps its
   predecessor shares lines with it; ranges of adjacent windows may overlap.

The result is stored in the passage metadata as `start_line`, `end_line`
(existing keys; `range_reason` when null). Overflow-split pieces (CI-06) keep
their sub-range logic, which now subdivides the window's range; the two must
agree (a test checks it).

### 3. Reasons for a null range (every null is explicit)

| Reason | Meaning |
| --- | --- |
| `artifact range not verified` | The artifact has no verified range (#412 and #417) |
| `window offset not reported` | Produced by a chunker that does not report offsets |
| `passage does not match artifact text at reported offset` | The offset check failed |
| `passage split; range not established` | An overflow piece set that did not reassemble |
| `line span not persisted at ingestion` | A vector written before #412 (unchanged) |

`artifact split into several passages` is retired for generations written
after this change; older vectors keep it until rewritten.

### 4. Incremental reuse (#196)

Reuse is by byte-identical file under an unchanged chunking and embedding
config, so a reused artifact has identical windows at identical offsets and its
ranges cannot have moved. Its stored vectors, however, were written without
window ranges. Two parts:

- **New and changed files** get ranges at embed time (section 2).
- **Reused artifacts** are updated by a metadata-only patch carried by the
  existing retag request to the vector store: for each reused document the
  ingestion service recomputes the windows (deterministic under an unchanged
  config) and sends `(chunk_index, text_sha256, start_line, end_line)`; the
  vector store patches a row only when its stored passage digest equals the sent
  digest and it still belongs to the expected prior generation, and reports the
  rows it skipped. Skipped rows keep their current reason. No text, vector or
  ordinal is touched.

This is the one change outside the ingestion service (vector store request
shape). **Decision (owner, 2026-11-21): the reuse patch is included.** Without
it, unchanged files would keep missing range metadata until a forced full
rebuild, which would undercut incremental ingestion.

The patch introduces a correctness boundary between the ingestion service and
the vector store. It must satisfy all of:

1. **Artifact and passage identity:** a row is patched only if its document id
   matches the artifact and its stored passage digest equals the digest sent.
2. **Generation fence:** the row still belongs to the expected prior
   generation; otherwise the whole update is rejected.
3. **Location metadata only:** only `start_line`, `end_line` and `range_reason`
   in the passage's source metadata may change.
4. **Nothing else changes:** embeddings, passage text, chunk ordinals and the
   chunking config version are untouched.
5. **Rejection leaves the record unchanged:** a failed generation or digest
   check writes nothing for that row (a generation failure writes nothing at
   all), and the skipped rows are counted and reported, never silently dropped.
6. **Tests cover both outcomes:** successful reuse, and each rejection path
   (digest mismatch, stale generation, unknown document), asserting the stored
   record is byte-for-byte unchanged after a rejection.

The patch is applied in the same request that moves the rows to the new
generation (as the existing provenance patch is), so a row never carries the
new generation with an old range.

### 5. Generation consistency

- A window's range is relative to the artifact range of the same generation,
  computed in the same ingestion, from the stored text of that generation.
- The reuse patch is fenced by the prior generation id, exactly as the existing
  provenance patch, and applies in the same request that moves the rows to the
  new generation.
- The orchestrator already returns `generation_id` in the citation and never
  derives or repairs a range; that does not change.

## Acceptance (retained from #416, on a Mealie rebuild at `1624c22`)

1. The share of passages with a verified range rises from 25.8% to at least 85%
   of passages whose artifact range is verified (target stated before the run).
2. **Zero incorrect ranges.** For every passage with a range in a random sample
   of at least 1,000, plus every passage that reported a non-null reason other
   than the pre-#412 one, the lines read back through
   `GET /v1/repos/{id}/source/read` at the same generation contain the passage
   text. "Contain" means: the joined lines, with the first line's text before
   the window start and the last line's text after the window end allowed, hold
   the window text exactly.
3. Every remaining null carries one of the reasons above.
4. A `/v1/rag` citation set re-measured on the same questions reports range
   yield per citation, before versus after.

## Verification and regression tests

| Case | Check |
| --- | --- |
| Identity | `line_windows` output equals the offset variant's text for generated and fixture inputs; ordinals, counts and `ChunkerFactory.VERSION` unchanged |
| Overlapping windows | Adjacent windows with overlap get overlapping ranges that each resolve |
| Repeated text | An artifact containing the same block three times: every window gets its own correct range; none is null for being repeated, none points at another copy |
| Long line | A single line over budget split into several windows: ranges name that line and resolve |
| First, last and single window | Boundaries map to the artifact's first and last lines |
| Mismatch | A corrupted offset yields null with the offset reason, never a wrong range |
| Unverified artifact | Windows get `artifact range not verified` |
| CRLF and lone CR | Ranges resolve against the stored (newline-normalized) text |
| Multi-byte text | Offsets are character offsets, not bytes; ranges still resolve |
| Overflow pieces | Piece ranges lie inside, and are consistent with, the window range |
| Reuse patch, success | An unchanged file re-ingested incrementally: its reused passages gain ranges; text, vectors, ordinals and chunking version are unchanged |
| Reuse patch, digest mismatch | The row is untouched, counted and reported; the rest of the batch still applies |
| Reuse patch, stale generation | The request is rejected; no row changes |
| Reuse patch, unknown document or row | Reported, nothing written for it |
| Reuse patch, preservation | After every rejection the stored row equals its prior state exactly (text, vector, ordinal, metadata) |
| Reuse patch, scope | Only `start_line`, `end_line` and `range_reason` differ after a successful patch |
| Pre-#412 vectors | Still report `line span not persisted at ingestion` |
| Live audit | The `source/read` read-back above on a real rebuild and on an incremental re-ingest with no file changes |

## Non-goals

Changing windows, chunking, embeddings or the chunking version; the same-line
prefix change (#417, which raises the number of verified artifacts and is
independent); Markdown; retrieval or ranking; any search-based location of
passages.

## Operator notes

No new migration is needed (the columns exist; window ranges live in passage
metadata). To populate ranges for an existing repository, rebuild it fully, or
(if the reuse patch is included) run an incremental ingest.
