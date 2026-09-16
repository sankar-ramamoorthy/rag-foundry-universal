# Feature specification: bounded repository ingestion memory

Created: 2026-09-16
Status: Ready for implementation; acceptance evidence pending
Tracking issue: #160
Roadmap: Phase 4 / WP-R1
Related: [programme](../005-production-correctness/spec.md),
[design review](/DOCS/audit/2026-09-16-bounded-ingestion-memory-design-review.md)

## Outcome and scope

Complete ingestion of the pinned DocsGPT incident fixture under a declared
memory ceiling with complete, unchanged normalized graph and vector content.
Bound embedding working memory independently of repository chunk count.
Repository-wide structural resolution remains unchanged and is NOT claimed
to use constant memory. Uploaded document/PDF conversion is outside this fix.

The reported approximately 23,354 text-bearing items must be counted
independently as nodes and chunks. One 128000-character node produces 143
chunks with the actual chunker.

## Governing references and disclosed drift

Preserve ADR-030/031/036/038/040/041/042 by reference. Actual code sub-chunks
artifacts despite ADR-040/041's historical 1:1 wording. Preserve actual chunk
boundaries and embedding inputs; disclose this drift rather than silently
changing semantics. The missing ADR-038 factory is #165; no new construction
site is allowed. Vector service retains ownership of its own DB tables.

## Required stories

US1: full pinned fixture completes without OOM.
US2: acknowledged write batches survive interruption, without promising resume.
US3: observable stages/progress start before first page allocation, including
empty-input completion and finite provider-failure deadlines.

## Requirements

FR-001: independently bound node-page count, active artifact UTF-8 bytes,
chunk-buffer count and chunk-buffer UTF-8 bytes. Validate positive settings.
FR-002: persist a buffer before accumulating its successor. Each HTTP batch
can commit separately; failure can leave part of a buffer committed.
FR-003: graph build/persist must exit a helper scope or explicitly release all
references before embedding. Removing a function argument is insufficient.
FR-004: preserve document-local chunk ordinals across buffer flushes.
FR-005: count/pages bind to repo_id AND ingestion_id. Detect disappearance or
replacement. Release depends on #161/#166 admission and mutation coordination.
FR-006: count/iteration share Python strip whitespace semantics. Empty input
completes with 0/0 progress, zero vectors and no embed call.
FR-007: normalized parity includes canonical IDs/edge endpoints, chunk ordinals,
exact text, metadata and deterministic-stub vectors. Ignore attempt telemetry
and UUID4 database/chunk IDs. Counts alone do not establish parity.
FR-008: no silent truncation, omitted artifact, new model or rechunking.
Reject artifacts over a configured byte ceiling BEFORE loading text into
Python, recording canonical ID and size as a visible failure. This explicitly
defines the supported-input envelope. The incident fixture must fit it.
If required fixtures exceed it, implement streaming or recalibrate with
evidence; do not silently increase the limit.
FR-009: expose stage, processed/total nodes, acknowledged chunks and observed
buffer maxima as additive status metadata. Persist a fresh JSON object.
FR-010: finite embedding connect/read deadlines; provider failure cannot falsely
complete the ingestion. A container limit is secondary defense.

## Success criteria

SC-001: pinned DocsGPT completes with the full emitted vector set under the
incident ceiling if recoverable, otherwise a separately declared new ceiling.
Record runtime/source SHA, model, settings and raw memory samples.
SC-002: live page/artifact/buffer maxima obey limits for N/4N small-artifact
and few-large-artifact fixtures. Fresh-process embedding incremental RSS at
4N <= 1.5 times N plus 32 MiB. Calibrate separately before acceptance; if
allocator behavior defeats the threshold, investigate and document any
criterion change before declaring success. Also report whole-run peak.
SC-003: killing/failing after N acknowledged HTTP batches preserves those
commits. Normal retry remains full rebuild: NO one-slice reprocessing promise.
SC-004: stage appears before allocation, progress is monotonic with eventual
advancement, and empty input completes at 0/0. Polls can repeat counts.

## Non-goals and gates

No durable queue, resume, incremental ingestion, zero-downtime publication,
factory refactor or chunk/model change. #161 and #166 remain separate issues
but production dependencies. No RAG quality evaluation is required if FR-007
holds; DB, failure and memory validation are mandatory. Semantic changes
trigger the constitution's quality evaluation gate.
