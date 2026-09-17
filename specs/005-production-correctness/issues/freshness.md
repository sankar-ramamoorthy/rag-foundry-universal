# WP-R5: generation-aware query/graph-cache freshness

Tracking issue: [#168](https://github.com/sankar-ramamoorthy/rag-foundry-universal/issues/168)
Status: Implemented on branch `feat/168-generation-aware-graph-cache`, CI
pending. See [ADR-051](/DOCS/adr/ADR-051-generation-aware-graph-cache.md)
(proposed) and [test-results evidence](/DOCS/test_results/2026-09-17-generation-aware-cache-issue-168.md).

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

`ingestion_service`'s `/v1/graph/repos/{repo_id}` (what `load_graph_for_repo`
calls) already, post-R3, filters `document_nodes` to one current-completed
`ingestion_id` and returns a `generation_status` field (`ready`/`building`/
`failed`/`unknown`) — so a *cold* load can no longer mix generations at the
data layer. But the response does not expose the generation identifier
itself, and `rag_orchestrator` discards `generation_status` entirely today;
nothing tells a warm cache it is stale.

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
- Pin a query to one generation at its start: resolve current generation
  once, use that resolved graph consistently for the whole request. If
  generation B completes while a query is already running against A, that
  query finishes on A — detect the change for the *next* query, don't
  chase it mid-request and don't combine snapshots within one request.
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

## Delivery tasks

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
