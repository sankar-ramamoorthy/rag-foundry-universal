# Persisted, verified source line spans

[Phase 6 implementation issue #412](https://github.com/sankar-ramamoorthy/rag-foundry-universal/issues/412).
Fills the line ranges left null by `specs/012-structured-citations/spec.md`.
Read against ADR-030/031 (identity and rebuild determinism are unchanged),
ADR-039/041 (artifact-level embedding; text on `DocumentNode`) and ADR-042.

## Contract

Every source-backed citation that advertises a line range resolves to the exact
source content it claims to represent. If the range cannot be established,
Foundry says so (null range with a reason) rather than inventing one.

A range is one-based, inclusive, in the source read API's line convention (LF
only, no phantom line after a terminal LF), over the node's **stored** module
text, the same text the source read serves. It names whole lines. The
artifact's text starts after the first line's indentation and may be followed on
its last line by trailing source (a comment, say); nothing else may differ.

## Design

| Piece | Behavior |
| --- | --- |
| Verification | `source_span.verified_range` accepts an extractor's end line only after the candidate lines are compared to the artifact text. Extractor spans are a hint, not trusted: a decorated Python definition's text starts at its first decorator while its span starts at `def`. Any mismatch stores no range. |
| Storage | `document_nodes.start_line` and `end_line`, nullable integers (additive migration `20261121_node_source_span`, no default, no rewrite). Refreshed on every upsert, including surviving rows. |
| Passages | A single passage that is the whole artifact carries its range. Several passages from one artifact carry none and the reason `artifact split into several passages`. |
| Overflow pieces | A piece never inherits the whole passage's range. If the pieces reassemble to the passage exactly, each gets the lines containing it; otherwise none, with a reason. |
| Reuse (#196) | Reuse is by byte-identical file, so a reused artifact's range cannot have moved. Vectors from generations ingested before this change have no range and stay null with the existing reason until a changed file or a full rebuild re-embeds them. |
| Citations | The manifest carries `start_line`, `end_line`, `range_reason` from chunk metadata. A citation uses a well-formed range as is, and otherwise null with the stored reason. The orchestrator never derives or repairs a range. |

## Acceptance cases

| Case | Observable result |
| --- | --- |
| Python, TypeScript files through the real extractors | Every stored range resolves against the stored module text; decorated and one-line definitions included |
| CRLF or lone-CR source | Ranges resolve against the stored (newline-normalized) text |
| Text that cannot be located | Range null; never a nearby guess |
| Overflow split | Pieces carry sub-ranges that contain them, or none |
| Pre-#412 vectors | Null with `line span not persisted at ingestion` |
| Malformed range in metadata | Citation range null |

## Not verified here

The Postgres path (migration applied, `persist_graph` writing the columns, a
live incremental ingest) was not run: Docker was unavailable. It is covered by
unit tests of the extractor-to-entity path and the column wiring only.

## Operator notes

Apply the migration before deploying. Populate ranges for existing repositories
with a full rebuild; an incremental ingest only fills changed files. Rust and
Java extractors are covered by the same verification, but only Python and
TypeScript were exercised in tests.
