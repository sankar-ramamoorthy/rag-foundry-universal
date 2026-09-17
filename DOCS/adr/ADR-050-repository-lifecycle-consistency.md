---
title: "ADR-050: Repository rebuild/delete lifecycle consistency"
date: 2026-09-17
type: adr
status: accepted
tags: [ingestion, lifecycle, recovery, concurrency, repository]
related:
  - "[WP-R3 specification](/specs/005-production-correctness/issues/lifecycle.md)"
  - "[ADR-049](/DOCS/adr/ADR-049-ingestion-ownership-recovery.md)"
  - "[ADR-030](/DOCS/adr/ADR-030-unified-artifact-graph.md)"
  - "[ADR-031](/DOCS/adr/ADR-031-canonical-identity-model.md)"
---

# ADR-050: Repository rebuild/delete lifecycle consistency

Tracking: #166 / WP-R3, merged via PR #178 (`351dc56a66c6b6f06e31f9738baf2407d9446652`).
Accepted: real-PostgreSQL CI-validated (run 35276463515 at head `f55ce5f`).
Linux rollout evidence remains a separate #171 gate, not covered here.

## Problem

Three related gaps, all sourced from `document_nodes.repo_id` being the only
place a repository's identity ever lived:

1. A repo delete that finishes vector/graph cleanup but crashes before
   removing its `ingestion_requests` rows cannot be retried to completion
   once `document_nodes` is empty — nothing is left to enumerate.
2. Nothing serialized a delete against a concurrent ingest/rebuild of the
   same `repo_id`; only the R2 global single-job admission slot happened to
   make this narrow in practice, not by contract.
3. `CodebaseGraphPersistence.persist_graph` atomically replaces **all** of a
   repository's `document_nodes` inside one transaction at graph-build time
   — well before embedding finishes and the ingestion is marked `completed`.
   That means a rebuild in progress silently becomes the only thing
   `document_nodes` holds for that `repo_id`, while its embeddings may still
   be incomplete; a `repo_id`-only graph read could therefore serve a
   not-yet-servable generation. Separately, `vector_store_service` has no
   equivalent replace-on-rebuild: every rebuild leaks the previous
   generation's vectors forever, since only a full repo delete ever calls
   `delete_by_ingestion_id`.

## Decision

**Persist `repo_id` on `ingestion_requests` independently of graph rows.**
Computed once, at HTTP accept time, from `build_repo_id(git_url or
local_path)` — a pure function of the source URL/path, needing no clone.
Backfilled for historical rows from `document_nodes` where recoverable
(migration `20260917_add_repo_id_to_ingestion_requests`). `repo_id` is now
the primary source for `list_ingestion_ids_for_repo`; `document_nodes` stays
a fallback union for any pre-migration row the backfill could not reach.

**Serialize repository mutation with a "repo" advisory-lock scope**, reusing
`ingestion_ownership.AdvisoryGuard` (ADR-049)'s lock-key namespacing.
Repository ingestion (`reserve_ingestion(..., repo_id=...)`) and repository
delete (`reserve_repo_mutation`) take the same scope keyed on `repo_id`; a
delete additionally rejects outright (409) if an accepted/running ingestion
already exists for that `repo_id`, rather than racing to acquire the lock.

**Resolve "the current generation" from `document_nodes`' actual owner, not
from ingestion status alone.** `document_nodes` can hold at most one
`ingestion_id`'s rows per `repo_id` at any moment (enforced by
`DocumentNode`'s `(repo_id, canonical_id)` unique constraint plus
`persist_graph`'s atomic replace) — trust that as ground truth for *which*
generation is present, then gate servability on that owner's
`ingestion_requests.status`. A read whose owner is not `completed` (a
rebuild still running, or one that later failed) reports `generation_status:
"building"`/`"failed"` and returns no nodes/relationships, rather than
serving a possibly-partial generation as if it were stable. This is a
narrower, corrected version of the original design's assumption that a prior
completed generation would remain visible during a rebuild — it does not,
given how `persist_graph` already works, and changing that would require a
non-atomic multi-generation graph schema this ADR does not adopt.

**Clean up superseded generations' vectors after a successful rebuild.**
Once a repo ingestion reaches `completed`, delete every other historical
`ingestion_id`'s vectors for the same `repo_id` (idempotent, same call
`delete_repo` already uses) and their now-fully-cleaned-up
`ingestion_requests` rows. Best-effort and non-fatal: a failure here leaves
stale vectors (degraded recall, dead document_id references dropped silently
by graph expansion) but does not retroactively invalidate the new
generation's own completion, and is logged for manual/#171 follow-up.

## Explicit non-goals

- No zero-downtime staged publication. The initial rebuild contract may make
  a repository explicitly unavailable (`generation_status: "building"`)
  while rebuilding; this ADR does not attempt to keep the prior generation
  servable during that window, because `persist_graph`'s existing atomic
  replace already destroys it before embedding starts. Building that would
  require a materially different graph-storage design, out of scope here.
- No distributed transaction across vector cleanup and
  `ingestion_requests`/graph mutation across services. The superseded-
  generation vector cleanup is best-effort; #171 owns closing that gap with
  monitoring/alerting, not this ADR.
- No change to canonical IDs (ADR-030/031) or to `pipeline_factory.py`
  ownership (ADR-038); existing factory drift (#165) remains disclosed, not
  repaired incidentally.

## Verification required

Real PostgreSQL tests must prove: `repo_id` survives graph deletion and a
retried delete completes; an attempt that never wrote a node is still
enumerable and deletable; the repo-scope lock serializes ingest against
delete in both directions; `generation_status`/`resolve_current_generation`
correctly report `unknown`/`building`/`ready`/`failed`, including the case
where a rebuild's graph-build step has already run but embedding/completion
has not; a completed generation survives a later failed attempt that never
touched `document_nodes`; superseded-generation cleanup identifies exactly
the non-current historical ids. Local mock tests alone (route-level
ordering/idempotency) cover HTTP orchestration only, not DB durability.
Target Linux release evidence is tracked separately in #171.
