---
title: "ADR-055: Read-only node-text endpoint for statement-level evidence delivery"
date: 2026-10-28
type: adr
status: accepted
tags: [ingestion-service, api, evidence, statement-level-delivery, issue-276]
related:
  - "[Issue #276](https://github.com/sankar-ramamoorthy/rag-foundry-universal/issues/276)"
  - "[Statement-level delivery contract (frozen)](/DOCS/evaluations/code-evidence-e1/statement-level-contract.md)"
  - "[ADR-041 code artifact persistence](/DOCS/adr/ADR-041-code-artifact-persistence-embedding-strategy.md)"
  - "[ADR-052 passage selection and provenance](/DOCS/adr/ADR-052-evidence-delivery-context-selection.md)"
  - "[ADR-051 generation-aware graph cache](/DOCS/adr/ADR-051-generation-aware-graph-cache.md)"
  - "[Issue #271 / PR #272: graph export off the event loop](https://github.com/sankar-ramamoorthy/rag-foundry-universal/pull/272)"
---

# ADR-055: Read-only node-text endpoint for statement-level evidence delivery

**Status: Accepted (2026-10-28).** The decision to add this endpoint is accepted.
**Nothing is implemented.** Acceptance does not authorize the statement-level
experiment or the implementation: the frozen
[contract](/DOCS/evaluations/code-evidence-e1/statement-level-contract.md) governs the
experiment, and the endpoint needs its own implementation issue. The numeric limits
below are starting values to be measured and set at implementation.

Roadmap phase: Phase 6, workstream E.

## Context

The statement-level delivery experiment needs the original source text of a function
node, by canonical id, to build verbatim excerpts with their enclosing structure.
ADR-041 persists that text on `DocumentNode.text`.

`ingestion_service` owns all database access (a hard invariant); `rag_orchestrator`
and the other services must go through its HTTP API. A review of the existing
surface found that **no endpoint returns `DocumentNode.text` by canonical id**:

| Existing endpoint | Why it does not serve this need |
| --- | --- |
| `GET /v1/graph/repos/{id}/nodes`, `POST .../nodes/lookup` | return `GraphNode` (ids, path, title, type, provenance), no text |
| `GET /v1/graph/repos/{id}` (full export) | same shape for every node; the export already loads and discards `text` (skipping it saved about 20% memory in the #270 reproduction) |
| `GET /v1/chunks/{ingestion_id}` | bare chunk strings for a whole ingestion; unlabeled |
| vector-store `search-by-doc` | chunk text; chunks are not source-faithful (stripped indentation, normalized blank lines, arbitrary cuts above 10,000 characters; see the #264 oracle) |

Source-faithful excerpts therefore cannot be built from any current API.

## Decision

Add one new read-only endpoint to `ingestion_service`:

`POST /v1/graph/repos/{repo_id}/nodes/text`

Request: `{"canonical_ids": [...], "generation_id": "<ingestion_id>"}`.
POST because the id list can be long (issue #107 documented the URL-length failure
of the GET lookup).

Response `200`: `{"generation_id": "...", "nodes": [{"canonical_id", "document_id",
"relative_path", "doc_type", "text", "text_sha256", "line_count"}], "missing":
[canonical ids not found in that generation], "too_large": [canonical ids over the
per-node cap]}`. The text is returned byte-for-byte as stored; the endpoint does no
parsing, trimming or normalization.

Behaviour:

- **Generation fence.** `generation_id` is required. It is compared with
  `resolve_current_generation(repo_id)` (the resolver the existing lookups use). A
  mismatch returns `409` carrying the current generation id; there is no silent
  fallback to a different generation. A repo with no completed generation returns
  `404`, as `/orient` does.
- **Repo scoping.** Rows are selected by `(repo_id, ingestion_id, canonical_id)`, so a
  caller cannot read another repository's nodes by canonical id
  (`uq_repo_canonical` is an existing unique index).
- **Bounds (proposed starting values, to be measured and set at implementation):**
  at most 20 ids per request; per-node text cap 256 KB (the largest function in the
  six E1 development cases is about 14.5 KB); total response cap 1 MB. Over-cap
  nodes are listed in `too_large`, not truncated.
- **Responsiveness.** The handler is a plain `def` (thread pool), not an `async def`
  around synchronous database work, per the #271 defect.
- **Observability.** Log request counts, hit/missing counts and sizes; never log text.

## Alternatives considered

1. **Optional `include_text` on the existing lookup.** Smaller surface, but mixes
   identity lookup (a hot path used by the orchestrator's graph expansion) with bulk
   content, and invites accidental large payloads. Not preferred; the owner may
   still choose it if the separate endpoint is judged too heavy.
2. **Add `text` to `GraphNode`.** Rejected: multiplies the full-graph export payload
   and memory for every node (the #270 reproduction measured about 20% less peak
   memory when the export skipped `text`), for a feature that needs a handful of
   nodes.
3. **Reconstruct text from chunks.** Rejected: not source-faithful, which is the
   property the experiment depends on.
4. **Orchestrator reads source from git or the filesystem.** Rejected: the system is
   read-only and the orchestrator holds no checkout; it would bypass the ingested
   generation and its fencing.
5. **Orchestrator reads the database directly.** Rejected: violates the
   `ingestion_service` ownership invariant.

## Consequences

- One new API surface to document, test and maintain.
- It exposes whole function bodies rather than chunks. This is the same underlying
  data already returned as chunk text by vector search, so it is not a new class of
  data, but it is a more convenient, larger read. The project currently has no
  per-user authorization (the security baseline is a separate roadmap item); this ADR
  does not change that and does not claim to.
- Adds load: a statement-mode query makes one extra request of bounded size per
  query. This has not been measured.
- Python only is *not* enforced here: the endpoint is language-agnostic; the
  contract limits v1 to Python.

## Verification plan (for the later implementation issue, not done)

Contract tests for: generation mismatch (`409`) and no-generation (`404`); missing
ids; id and size limits; `text_sha256` equals the SHA-256 of the stored text and the
text equals the stored value byte-for-byte; no cross-repository leakage; and a
responsiveness test that another route stays fast while a large request runs
(modelled on `test_graph_export_event_loop.py`).

## What would change this decision

Evidence from the experiment that statement-level delivery does not help (NO-GO), or
that the target-selection problem (#275) must be solved first and makes this
unnecessary. In either case this ADR would be superseded by a new one. Until an
implementation issue exists the endpoint stays unbuilt, and no candidate run can
happen before a trustworthy matched control replay exists (#270).
