---
title: "Incremental retag timeout (#416) and how a generation is promoted"
date: 2026-11-22
type: note
status: current
summary: "The first live incremental ingest of Mealie after #416 failed with a vector-store read timeout and left the repository in a split, unservable state. Cause, the fix (one UPDATE per row, smaller requests, explicit timeout handling), and the documented promotion and recovery behavior, with the test that pins it."
tags: [incremental-ingestion, retag, generation, atomicity, issue-416, live-finding]
related:
  - "[Issue #416](https://github.com/sankar-ramamoorthy/rag-foundry-universal/issues/416)"
  - "[Spec 015](/specs/015-per-window-source-ranges/spec.md)"
  - "[Baseline and live checks](/DOCS/test_results/2026-11-21-412-mealie-span-baseline.md)"
---

# Incremental retag timeout and generation promotion

## What happened (observed)

After deploying #416 (SHA `70c645e`) a no-change incremental ingest of the Mealie
repository (7,758 nodes, 17,676 passages) embedded nothing, correctly, then failed
in the reuse stage with `vector_store_service ... Read timed out (read timeout=90)`.
Read-only SQL showed 13,721 passages already moved to the new generation, 3,955
still on the old one, all 21,621 nodes on the new one, and the ingestion
`failed`. The repository reported `generation_status: failed` and was unservable
until a full rebuild restored it. The small integration tests had passed.

## Cause

1. **Two writes per row.** The range patch was a second UPDATE of rows the retag
   had just updated in the same transaction. Every UPDATE that changes an indexed
   column rewrites the row's index entries, including the HNSW vector index, so
   the work roughly doubled. A request of up to 1,000 documents and 4,000 patches
   outlasted the client's 90 second timeout.
2. **A timeout was not handled.** The fallback "retry without ranges" caught only
   HTTP error responses. A `requests` timeout is not one, so it propagated and
   the run failed. (A timeout is also not safe to retry; see below.)
3. **Requests were large.** The batch limit bounded documents, not patches.

## Fix

- **One UPDATE per row.** Rows with a verified range are moved to the new
  generation and given their range (and refreshed provenance) in one statement,
  still digest-guarded and fenced to the expected prior generation. The plain
  retag then moves only what is still at the prior generation. Each row is
  written once. Atomicity per request is unchanged (one connection, one
  transaction).
- **Smaller requests.** At most 500 patches per request (a document is never
  split), and a 180 second timeout.
- **Explicit timeout handling.** A timeout or lost connection raises
  `RetagIncompleteError` and fails the ingestion. It is never retried (with or
  without ranges) and never treated as "documents missing, re-embed them", because
  the request may have committed, and re-embedding would duplicate vectors. The
  error says how many documents had already moved.
- **Realistic-size test.** An integration test moves and patches 3,000 passages
  across 150 documents in one request and requires it to finish inside 60 seconds.

## How a generation is promoted, and why a failure is safe

Observed in `ingestion_service/src/core/db_utils.py` and `codebase_ingest.py`:

- A repository is served only when the generation that owns its `document_nodes`
  has `ingestion_requests.status == "completed"` (`resolve_current_generation`;
  `generation_status` reports `building`, `failed` or `ready`).
- `completed` is written once, at the end of the run, after graph persistence,
  embedding and reuse retagging (`mark_completed`). Any exception marks the run
  `failed` (`mark_failed`).
- So a run that dies between retag requests is `failed`: the physical rows are
  split across two generations, but nothing is served from them. A partially
  promoted generation is never eligible for serving.
- Recovery is automatic: the next ingestion finds no completed prior generation
  (`resolve_current_generation` is `None`), so it is a full ingestion, not an
  incremental one, and replaces the split state with one consistent generation.
- Cost of this design: a failed incremental run leaves the repository unservable
  until the next run completes (here about 33 minutes for Mealie). It protects
  correctness, not availability. Keeping the prior generation servable during a
  rebuild is a separate, larger change (issues #285 and #286 concern it).

## Tests

- Vector store unit: one move-and-patch statement per batch plus one plain retag;
  location-only write; digest and prior-generation guards; provenance in the same
  statement; skip reasons.
- Vector store integration (real Postgres): everything that was tested before,
  plus the 3,000-passage single-request case.
- Ingestion unit: timeouts are never retried; a timeout part-way reports how many
  documents had moved; small requests and a generous timeout.
- Ingestion integration (real Postgres and vector service): a timeout on the second
  retag request leaves the run `failed`, the repository not servable, vectors
  split across two generations; the next run is a full ingestion and ends with one
  generation, no duplicates, and the original passage counts.

## Not verified

The fix has not been deployed or run against Mealie. The next live check is a
no-change incremental ingest after the owner deploys it.
