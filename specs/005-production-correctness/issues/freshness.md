# WP-R5: generation-aware query/graph-cache freshness

Tracking issue: [#168](https://github.com/sankar-ramamoorthy/rag-foundry-universal/issues/168)
Original delivery: merged via PR #183; ADR-051 records acceptance and real-PostgreSQL
CI evidence. Linux rollout evidence remains a separate gate. See
[ADR-051](/DOCS/adr/ADR-051-generation-aware-graph-cache.md) (accepted) and
[test-results evidence](/DOCS/test_results/2026-09-17-generation-aware-cache-issue-168.md).

Roadmap: Phase 4 production correctness, WP-R1 through WP-R8.

## Scope split (2026-09-17)

Reconstructing #168 after WP-R3 (#166) landed showed its original text
bundled three unrelated correctness domains. Split so each has one owner
and one acceptance boundary:

- **This file/issue (#168): generation-aware query/cache freshness only.**
- Git ref / resolved-SHA / config-fingerprint ingestion provenance ->
  [#180](https://github.com/sankar-ramamoorthy/rag-foundry-universal/issues/180).
- Evaluation three-revision (runtime/corpus/ground-truth) provenance ->
  [#181](https://github.com/sankar-ramamoorthy/rag-foundry-universal/issues/181).

R3 supplies exactly the generation-identity model this file's concern needs
(a repository's document_nodes have one current-completed-generation
`ingestion_id`, resolvable via `ingestion_requests.repo_id` + status). R3
deliberately did not propagate that identity to the orchestrator's cache —
that propagation is this issue's entire job.

## Problem and evidence

Audit A7: `rag_orchestrator`'s
[get_cached_graph](/rag_orchestrator/src/retrieval/codebase_utils.py#L199)
keeps a whole graph indefinitely in a process-global, unbounded, TTL-less
`Dict[str, CodebaseGraph]` keyed only by `repo_id`. Re-ingesting the same
repo changes what `ingestion_service`'s DB/vector store hold, but a warm
worker keeps traversing the stale cached graph — nothing reloads it. A
query can therefore combine vector evidence from a new generation with
graph traversal from an old one:

```text
Repo generation A ingested -> orchestrator loads graph A into memory
Repo re-ingested -> generation B completes; DB/vectors now represent B
orchestrator cache still holds graph A
query uses: vector evidence from B, graph traversal from A
```

R3 added owner/completion gating and `generation_status` to
`/v1/graph/repos/{repo_id}`. The original specification inferred that cold loads
could no longer mix generations. CI-01 found that separate reader sessions and
statements did not establish that guarantee; the response also lacks generation
identity and the loader discards status. The accepted clarification below binds
these reads and validates the actual exported identity.

## Proposed plan

- Expose current generation identity (`ingestion_id`) from
  `ingestion_service`'s repository-resolution API — cheaply, without
  requiring a full graph fetch just to check it. A lightweight generation
  lookup (e.g. `GET /v1/repos/{repo_id}/generation` or an added field on an
  existing summary endpoint), not `/v1/graph/repos/{repo_id}`'s full
  nodes+relationships payload.
- Key `rag_orchestrator`'s `_repo_graphs` cache on `(repo_id,
  generation_id)` instead of `repo_id` alone; bound it (eviction, not
  indefinite growth — LRU or similar, sized for the realistic number of
  concurrently-queried repos).
- Pin graph traversal to one validated materialized snapshot. Traversal can
  finish on A if B subsequently commits. This permission applies to graph
  snapshot consistency; it does not remove existing RAG/evidence outer fences
  that retry/fail on generation drift across vector, graph and passage reads.
- Honor ADR-031 canonical identity: no generation suffix appended to
  canonical IDs. Generation is cache/query metadata, never part of
  identity.

## Acceptance and verification

- Re-ingest a changed edge under the same `repo_id`; a warm worker's next
  query must observe the new graph, not the stale cached one.
- Delete/recreate under the same `repo_id` cannot reuse old cached content.
- A generation change landing mid-query does not produce a response that
  mixes two generations' graph/vector evidence within one request.
- Cache size is bounded under repeated repo churn (eviction verified, not
  assumed).
- Checking "has the generation changed" does not require a full graph
  fetch (verify via request count/latency, not just correctness).
- Real PostgreSQL + real `rag_orchestrator`<->`ingestion_service` HTTP
  round-trip test, not mocks alone, for the re-ingest-observed-by-warm-
  worker case specifically (this is the scenario audit A7 and the original
  incident concern both centered on). Delivered as: a real-Postgres
  integration test against the actual FastAPI route (ingestion side) plus
  unit tests mocking the HTTP seam (orchestrator side) — not a literal
  two-live-process round trip; see ADR-051's non-goals for why that gap is
  disclosed rather than silently claimed closed.

## CI-01 clarification (accepted 2026-11-10)

Implementation was separately authorized under #335 and delivered through
[PR #336](https://github.com/sankar-ramamoorthy/rag-foundry-universal/pull/336).
See the [PostgreSQL verification](/DOCS/test_results/2026-11-10-ci01-graph-snapshot-verification.md)
for new evidence; original delivery evidence below remains historical.

The [graph snapshot contract](../contracts/repository-graph-snapshot.md) and
amended ADR-051 require the cache label to match the actual validated export,
whose identity/status/content share one snapshot under amended ADR-050. A cheap
lookup alone does not establish a later export's identity or consistency.

- Warm hits require a coherent ready cheap check matching the entry's identity;
  errors/non-ready/missing identity cannot authorize stale fallback.
- Cold/forced loads send `expected_generation_id`, validate the HTTP outcome,
  repository, explicit ready status, matching ingestion UUID, count and graph
  shape before constructing a usable graph or inserting it into the cache.
- Conflict, non-ready, legacy/invalid envelope and transport failures must not
  become authoritative empty graphs. Direct TRACE/IMPACT distinguish unavailable
  from absent-at-snapshot and expose the graph's repository/generation identity.
- Preserve bounded LRU storage, synchronization and the existing RAG/evidence
  whole-request generation fences. Concurrent loads cannot mislabel content or
  bypass the next cheap check. Coalescing is optional.

Acceptance requires the contract's PostgreSQL race matrix and actual
route/HTTP-client/loader/cache composition for lookup A/export B, unavailable and
legacy rejection, warm reuse, forced/concurrent loads and consumer identity/fences.
Producer support precedes validating consumers; missing identity fails closed.
Original sequential tests and the synthetic investigation do not close these
gates. No application changes are authorized by accepting this clarification.

## Original delivery tasks

- [x] Finalize issue-linked specification, plan, contracts, and acceptance
  tests for this narrowed scope (this file; ADR-051).
- [x] Implement scoped fix on a dedicated branch
  (`feat/168-generation-aware-graph-cache`); preserve service ownership
  (`rag_orchestrator` doesn't gain DB access; it still only talks to
  `ingestion_service` over HTTP) and model provenance.
  - New `GET /v1/repos/{repo_id}/generation` on `ingestion_service`.
  - `get_cached_graph` keyed on `(repo_id, generation_id)`, LRU-bounded
    (`GRAPH_CACHE_MAX_REPOS`), thread-safe.
  - No-completed-generation short-circuits to an empty graph without a
    full fetch.
- [x] Run relevant unit/integration checks; record limitations honestly —
  see evidence doc. All four CI checks pass at head `ceabbe4` (run
  35281171853), including 20 real-Postgres repository-lifecycle/generation
  tests (16 from #166 plus 4 new for this endpoint).
- [x] Update OKF knowledge-base links, current status, roadmap, ADR-051,
  and evidence doc.
- [x] Commit, push, review CI (green), PR #183 open — merge pending final
  review/authorization.
- [ ] Record deployment-specific gates (Linux/#171) separately from code
  completion.

## Explicit non-goals

- Git ref acceptance, resolved-commit-SHA recording, ingestion config
  fingerprint — [#180](https://github.com/sankar-ramamoorthy/rag-foundry-universal/issues/180).
- Evaluation three-revision (runtime/corpus/ground-truth) provenance —
  [#181](https://github.com/sankar-ramamoorthy/rag-foundry-universal/issues/181).
- No change to ADR-030/031 canonical identity.
- No zero-downtime staged publication guarantee beyond what R3/ADR-050
  already established — this issue is about readers noticing a *completed*
  generation change, not about serving a repo mid-rebuild.
