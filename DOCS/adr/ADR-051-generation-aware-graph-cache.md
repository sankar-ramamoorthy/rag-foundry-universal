---
title: "ADR-051: Generation-aware rag_orchestrator graph cache"
date: 2026-09-17
type: adr
status: accepted
amended: 2026-11-10
tags: [rag_orchestrator, caching, freshness, generation, repository]
related:
  - "[CI-01 implementation verification](/DOCS/test_results/2026-11-10-ci01-graph-snapshot-verification.md)"
  - "[CI-01 graph snapshot contract](/specs/005-production-correctness/contracts/repository-graph-snapshot.md)"
  - "[WP-R5 specification](/specs/005-production-correctness/issues/freshness.md)"
  - "[ADR-050](/DOCS/adr/ADR-050-repository-lifecycle-consistency.md)"
  - "[ADR-030](/DOCS/adr/ADR-030-unified-artifact-graph.md)"
  - "[ADR-031](/DOCS/adr/ADR-031-canonical-identity-model.md)"
---

# ADR-051: Generation-aware rag_orchestrator graph cache

Tracking: #168 / WP-R5 (narrowed scope; split from #180/#181 on 2026-09-17),
merged via PR #183 (`cb3622056cd58a08961e450c8b9c2383b47af6e1`).
Accepted: real-PostgreSQL CI-validated (run 35281353921 at head `0adbb3b`).
Linux rollout evidence remains a separate #171 gate, not covered here.

## Problem

`rag_orchestrator`'s `_repo_graphs` cache
(`retrieval/codebase_utils.py::get_cached_graph`) was a process-global,
unbounded, TTL-less `Dict[str, CodebaseGraph]` keyed only by `repo_id`.
`build_repo_id` is deterministic per source URL (ADR-031), so a rebuild
reuses the same `repo_id` under a new `ingestion_id` — the cache had no way
to know its stored graph was stale, and nothing ever reloaded or evicted
it. A warm worker could keep answering from a pre-rebuild generation
indefinitely, combining new vector evidence (from `vector_store_service`,
filtered only by `repo_id`) with old graph evidence (from the stale cache).

R3/ADR-050 introduced actual-owner/completion gating. The original version of
this ADR asserted that this alone made cold exports internally consistent.
The [CI-01 investigation](/DOCS/audit/2026-11-10-ci01-generation-snapshot-investigation.md)
found separate reader sessions/statements and missing export identity; the
original claim was stronger than its evidence. The November 10 amendment below
defines the required composition without changing R3's mutation decision.

## Decision

**Expose generation identity cheaply.** New `GET
/v1/repos/{repo_id}/generation` on `ingestion_service`, wrapping
`db_utils.resolve_current_generation`/`generation_status` (#166) directly —
a single indexed lookup, not a full node/relationship export. A caller that
only needs to know "has this changed" must not pay for a full graph fetch
to find out.

**Key the cache on `(repo_id, generation_id)`, not `repo_id` alone.**
`get_cached_graph` calls the cheap generation endpoint on every invocation.
A cache hit requires a coherent ready lookup whose identity matches the stored
generation. Any mismatch (including "no entry yet") triggers a generation-fenced,
validated reload via `get_full_graph_from_api`/`load_graph_for_repo` under the
CI-01 contract. Only the selected
generation is ever kept per `repo_id` — a stale entry is replaced outright,
not kept alongside the new one, so the cache never holds two generations of
the same repository simultaneously.

**One structural operation, one materialized graph snapshot.** A validated graph
A can finish traversal even if B subsequently commits. A separate lookup plus
an unvalidated export cannot establish that the loaded graph was A. Nor does
snapshot-consistent graph traversal establish generation alignment across vector,
graph and passage reads. Preserve existing RAG/evidence outer fences and their
retry/failure behavior on drift; finishing graph traversal on A is not permission
to finish a mixed-generation whole request.

**Bound the cache by repo count, not by generation.** The original defect
was unbounded growth across every `repo_id` ever queried, not "too many
generations of one repo" (structurally impossible to hold more than one, by
construction above). `_repo_graphs` is now an `OrderedDict` with LRU
eviction at `GRAPH_CACHE_MAX_REPOS` (default 32) distinct repositories.

**No completed generation, no usable graph.** A cheap check reporting
`building`/`failed`/`unknown`, missing identity or transport failure cannot
authorize fetching/reusing a ready graph or writing a cache entry. Propagate
unavailability distinctly from absence. The original implementation returned an
empty `CodebaseGraph()` here; CI-01 requires explicit unavailable semantics so
structural consumers cannot turn missing data into supported-looking absence.

**Thread safety.** A `threading.Lock` guards all reads/writes of
`_repo_graphs`, since concurrent requests can call `get_cached_graph`
simultaneously and the previous implementation had no such guard.

## CI-01 export validation (accepted 2026-11-10)

The [graph snapshot contract](/specs/005-production-correctness/contracts/repository-graph-snapshot.md)
is authoritative for the envelope, outcomes and race acceptance. Owner acceptance
authorizes this clarification only, not application changes. Original delivery
evidence below remains historical, not verification of this amendment.

Implementation was subsequently authorized separately under #335; local
[verification](/DOCS/test_results/2026-11-10-ci01-graph-snapshot-verification.md)
records the new evidence. Merge/deployment state is tracked in `DOCS/status.md`.

Cold and forced loads send `expected_generation_id` for their selected ingestion
UUID. Before constructing a usable graph or caching it, validate the export's
repository, explicit ready status, non-null identity matching the expectation,
node count and graph shape. The cache label comes from this validated export,
never from an unrelated earlier lookup. Reject 409, non-ready, malformed, legacy
identity-missing and transport-failure results without stale fallback or insertion.

Warm reuse keeps the cheap generation check; its identity/status must be coherent
at its own read boundary. A check at A permits reuse of a correctly identified
A snapshot even if B commits just afterward. Every later invocation checks again.
Concurrent loads must preserve payload/label coupling and cannot bypass the next
freshness check. Keep bounded LRU storage and synchronization; coalescing is optional.
Direct TRACE/IMPACT must expose the graph identity and distinguish unavailable
from absent-at-snapshot. Non-ready empty wire collections are not ready graphs.

Producer support ships before validating consumers; new consumers fail closed
against older envelopes. Both sides must be verified before claiming CI-01 closure.
The preferred single repeatable-read export transaction is described in amended
ADR-050. No canonical-ID, storage-generation retention or vector-filtering change
is adopted here.

## Explicit non-goals

- No vector-store-side generation filtering. `vector_store_service` search
  still filters by `repo_id` only; a rebuild's superseded-generation
  vectors are cleaned up best-effort by R3 (#166), not guaranteed
  synchronously with this cache's freshness. Graph snapshot consistency does
  not certify that vector seeds belong to the same generation in every race
  window — closing that fully would require vector search to also key
  on `ingestion_id`, out of scope here.
- No canonical ID change (ADR-030/031). Generation is cache/query metadata
  only, never appended to or mixed into canonical IDs.
- No live two-service HTTP round-trip test in CI (a running
  `rag_orchestrator` process actually calling a running `ingestion_service`
  process). Unit tests mock the HTTP seam on the orchestrator side;
  integration tests exercise the new endpoint against real Postgres on the
  ingestion side. Both together cover each side of the contract, not an
  end-to-end process test — disclosed, not claimed.
- Ingestion source-revision provenance (#180) and evaluation three-revision
  provenance (#181) remain separate, unimplemented follow-ups.

## Original verification (September 2026)

Unit tests (`rag_orchestrator/tests/test_graph_cache_generation.py`) prove:
cold load caches; warm hit on matching generation skips refetch; a
generation change is observed and replaces (not duplicates) the cached
entry; `force_reload` bypasses a matching-generation cache; no-completed-
generation returns empty without fetching or caching; LRU bound and
recency-based eviction. `rag_orchestrator/tests/test_repo_generation_lookup.py`
proves the cheap-check HTTP client degrades to `unknown` on network error or
non-200 rather than raising. Real-Postgres integration tests
(`ingestion_service/tests/api/test_repo_generation_integration.py`) prove
the new endpoint's contract end to end through the actual FastAPI route —
including the specific rebuild-in-progress case (graph already replaced,
not yet completed) and the re-ingest-under-same-repo_id case #168's
acceptance criteria centers on.

CI-01 additionally requires real PostgreSQL barrier-controlled export races and
HTTP-client/loader/cache composition, including legacy/error rejection, unavailable
semantics, concurrent loads, direct structural identity and retained outer fences.
The full matrix and connection-cleanup requirements are in the graph contract;
none is claimed executed by the original tests or this documentation amendment.
