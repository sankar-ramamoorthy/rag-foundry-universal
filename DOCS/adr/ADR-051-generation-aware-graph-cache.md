---
title: "ADR-051: Generation-aware rag_orchestrator graph cache"
date: 2026-09-17
type: adr
status: proposed
tags: [rag_orchestrator, caching, freshness, generation, repository]
related:
  - "[WP-R5 specification](/specs/005-production-correctness/issues/freshness.md)"
  - "[ADR-050](/DOCS/adr/ADR-050-repository-lifecycle-consistency.md)"
  - "[ADR-030](/DOCS/adr/ADR-030-unified-artifact-graph.md)"
  - "[ADR-031](/DOCS/adr/ADR-031-canonical-identity-model.md)"
---

# ADR-051: Generation-aware rag_orchestrator graph cache

Tracking: #168 / WP-R5 (narrowed scope; split from #180/#181 on 2026-09-17).

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

R3/ADR-050 already fixed the underlying *data*-correctness half: a cold
`GET /v1/graph/repos/{repo_id}` now returns exactly one current-completed
generation's nodes, never a mix. It deliberately did not propagate that
generation identity to any caller's cache — that propagation is this ADR's
subject.

## Decision

**Expose generation identity cheaply.** New `GET
/v1/repos/{repo_id}/generation` on `ingestion_service`, wrapping
`db_utils.resolve_current_generation`/`generation_status` (#166) directly —
a single indexed lookup, not a full node/relationship export. A caller that
only needs to know "has this changed" must not pay for a full graph fetch
to find out.

**Key the cache on `(repo_id, generation_id)`, not `repo_id` alone.**
`get_cached_graph` calls the cheap generation endpoint on every invocation.
A cache hit requires the stored generation to still match; any mismatch
(including "no entry yet") triggers a real reload via the existing full
`get_full_graph_from_api`/`load_graph_for_repo` path. Only the current
generation is ever kept per `repo_id` — a stale entry is replaced outright,
not kept alongside the new one, so the cache never holds two generations of
the same repository simultaneously.

**One query, one generation.** `hybrid_retrieve` calls `get_cached_graph`
exactly once per request (its single graph-expansion step). Resolving the
generation once per call and using it consistently for that call therefore
means a single query can never mix two generations' graph evidence within
itself — a rebuild landing mid-request is invisible to that request and
observed by the *next* one, not chased mid-flight.

**Bound the cache by repo count, not by generation.** The original defect
was unbounded growth across every `repo_id` ever queried, not "too many
generations of one repo" (structurally impossible to hold more than one, by
construction above). `_repo_graphs` is now an `OrderedDict` with LRU
eviction at `GRAPH_CACHE_MAX_REPOS` (default 32) distinct repositories.

**No completed generation, no fetch.** If the cheap check reports
`building`/`failed`/`unknown` (no `ingestion_id`), `get_cached_graph`
returns an empty `CodebaseGraph()` without calling the full-graph endpoint
at all and without writing a cache entry — `ingestion_service` would only
return empty in that case anyway (ADR-050); the cheap check now avoids
paying for it.

**Thread safety.** A `threading.Lock` guards all reads/writes of
`_repo_graphs`, since concurrent requests can call `get_cached_graph`
simultaneously and the previous implementation had no such guard.

## Explicit non-goals

- No vector-store-side generation filtering. `vector_store_service` search
  still filters by `repo_id` only; a rebuild's superseded-generation
  vectors are cleaned up best-effort by R3 (#166), not guaranteed
  synchronously with this cache's freshness. A query's vector seeds and its
  graph expansion are therefore each internally consistent with *a*
  generation, but not formally proven to be the *same* generation in every
  race window — closing that fully would require vector search to also key
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

## Verification required

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
