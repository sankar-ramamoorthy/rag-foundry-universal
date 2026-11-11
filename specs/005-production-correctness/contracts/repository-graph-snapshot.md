---
title: "CI-01: Repository graph snapshot contract"
date: 2026-11-10
type: spec
status: accepted
summary: "Approved for implementation under #335; local verification is recorded separately"
related:
  - "[CI-01 implementation plan](/specs/005-production-correctness/ci01-plan.md)"
  - "[CI-01 PostgreSQL verification](/DOCS/test_results/2026-11-10-ci01-graph-snapshot-verification.md)"
  - "[Production correctness specification](/specs/005-production-correctness/spec.md)"
  - "[WP-R3 lifecycle](/specs/005-production-correctness/issues/lifecycle.md)"
  - "[WP-R5 freshness](/specs/005-production-correctness/issues/freshness.md)"
  - "[ADR-050](/DOCS/adr/ADR-050-repository-lifecycle-consistency.md)"
  - "[ADR-051](/DOCS/adr/ADR-051-generation-aware-graph-cache.md)"
  - "[CI-01 investigation](/DOCS/audit/2026-11-10-ci01-generation-snapshot-investigation.md)"
---

# CI-01: Repository graph snapshot contract

Initially accepted by the owner on 2026-11-10 for specification work only;
the owner subsequently approved implementation under
[#335](https://github.com/sankar-ramamoorthy/rag-foundry-universal/issues/335).
This contract clarifies WP-R3/WP-R5. Implementation and verification are tracked
in the linked plan/evidence, rather than inferred from acceptance alone.
The investigation remains historical evidence.

## Invariant and scope

For every ready export there exists one database snapshot S and one generation G
such that the repository's actual graph owner, that owner's completed status,
all returned node versions and all returned relationship versions are read from S.
The response identifies G using `ingestion_id`. Consumers must never label or
cache its graph as a different generation.

`ready` means completed and readable at S, not current when HTTP delivery or a
later answer finishes. An export may finish reading A while a rebuild or delete
commits afterward. A remains a valid materialized A snapshot. This does not
promise historical retrieval on a new request, zero-downtime publication, vector
consistency, passage consistency, or freshness for an entire multi-service request.
Canonical IDs remain unchanged.

## Endpoint and envelope

`GET /v1/graph/repos/{repo_id}?expected_generation_id=<UUID>`

The query parameter is optional. It denotes the existing ingestion UUID, not a
source commit or canonical-ID suffix. Malformed values return HTTP 422. Omitting
it selects the completed graph actually present at S; supplying it is a fence,
not a request to load archived data or to wait for a generation to complete.

Every HTTP 200 response contains these required fields, with no implicit defaults:

| Field | Required value |
| --- | --- |
| `repo_id` | The requested repository identity |
| `ingestion_id` | Non-null UUID string for `ready`; null otherwise |
| `generation_status` | `ready`, `building`, `failed`, or `unknown` |
| `nodes` | Existing `GraphNode` list; no new source-text field |
| `relationships` | Existing source-canonical-ID map of edge lists, including relationship metadata |
| `total_nodes` | Exactly `len(nodes)` |

Ready nodes belong to `(repo_id, ingestion_id)` at S. Each exported relationship
belongs to the repository at S and has both endpoints in the exported node set.
Node IDs are unique, and edge metadata is read within S too. Edges do not need a
new generation column: the writer's atomic repository replacement plus the
reader's shared snapshot supplies their consistency boundary. Integrity failures
(such as multiple graph owners or a violated export invariant) fail the export
with HTTP 500; they must not be converted into ready empty or partial results.

## Selection and outcome precedence

Resolve ownership and availability at S before checking the expected generation:

| State at S | HTTP / result |
| --- | --- |
| One graph owner G, its matching request is completed; no expectation or expectation G | 200, `ready`, `ingestion_id=G`, G's graph |
| Same ready owner G, expectation A differs | 409, explicit generation conflict; no graph |
| Graph owner is accepted/running | 200, `building`, null identity and empty graph |
| Graph owner is failed | 200, `failed`, null identity and empty graph |
| Graph owner lacks a matching request | 200, `unknown`, null identity and empty graph; log the inconsistency |
| No graph owner | 200, null identity and empty graph; `building`/`failed` from the latest repository attempt if active/failed, otherwise `unknown` |

An intact completed owner A remains servable even if a newer attempt is running
or failed without replacing graph rows. Once B replaces rows but is not completed,
the result is unavailable; do not fall back to A's completed request record.
Deleted and never-known repositories both resolve to `unknown` once their rows
are gone; no tombstone or distinct deletion state is introduced here.

For non-ready HTTP 200 results, `nodes=[]`, `relationships={}`, `total_nodes=0`.
These are explicit unavailable outcomes, including when an expectation was supplied;
they do not satisfy that expectation or assert that the source has no symbols.
Keeping status-bearing HTTP 200 for availability preserves the existing transport
convention; callers must inspect the envelope. `building` can be retried with a
bounded caller policy; `failed`/`unknown` need recovery, ingestion or renewed
resolution rather than an unbounded automatic retry loop.

A 409 response uses FastAPI's `detail` object with `code="generation_conflict"`,
`repo_id`, `expected_generation_id`, `ingestion_id=G` and
`generation_status="ready"`, all from S. It contains no graph. G is informational
and may change before the next call. Retry means re-resolving the caller's whole
generation selection; never silently substituting G into a request pinned to A.
Database/transport/time-limit failures remain errors, with no authoritative graph
result and no cache insertion. They must not be mapped to source absence.

## Empty graph versus unavailable

The current lifecycle resolves ownership through `DocumentNode` rows. With zero
nodes there is no graph owner, even if a completed ingestion request exists.
Therefore this contract does **not** permit a zero-node `ready` export. A completed
attempt alone cannot certify an empty current snapshot. If a selected owner yields
no nodes inside the same snapshot, fail the invariant rather than manufacture a
ready empty response. Supporting completed zero-node repositories would require
an explicit publication/ownership decision outside this clarification.

A ready graph with nodes and zero relationships is valid. A symbol absent from a
successfully loaded ready graph can be reported absent from that analyzed snapshot;
that is not proof of absence from all source code. An unavailable graph cannot
produce an authoritative symbol-not-found or no-impact answer.

## Preferred transaction design and feasibility

Use one export-scoped PostgreSQL `REPEATABLE READ`, read-only transaction on one
connection/session. Configure isolation before the first data statement. Resolve
the actual node owner, its request/status (and any unavailable fallback), validate
the expectation, read nodes and edges, and copy all response fields into ordinary
materialized values within that transaction. Helpers must accept the shared
session; calling helpers that open independent sessions does not meet the contract.
Do not lazily load ORM attributes or relationships after the transaction closes.

End the transaction and release the connection before sending the HTTP body or
doing other service/LLM work. No repository reader lock or global isolation change
is required. Retain the synchronous route's thread-pool execution. Errors,
timeouts and abandoned work must roll back/close reliably; a cancelled HTTP await
alone is not evidence that its worker released the database connection.

Source review at baseline `1a8fd587` supported feasibility with this design:

- Compose uses PostgreSQL 15 (`pgvector/pgvector:pg15`). The service permits
  SQLAlchemy `>=1.4,<2.0`; the local installed version is 1.4.54, with PostgreSQL
  drivers already declared. `database_session.py` has no explicit isolation level.
- `CodebaseGraphPersistence.persist_graph` performs node upserts, removal of absent
  nodes, and full repository edge replacement in one `session.begin()` transaction.
  Surviving document IDs are reused, so IDs alone cannot fence edge versions.
- `StatusManager.mark_completed` commits later, after embedding and completion
  metadata. A shared snapshot sees either the prior completed owner, a new
  non-ready owner, or the new completed owner, without combining these phases.
- Delete uses normal transactional row deletion/cascades, followed by request
  cleanup; superseded request cleanup also uses normal deletes. Old row versions
  remain readable in an already-established snapshot. No schema migration or
  multi-generation retention is required for this export boundary.
- At that baseline, `_document_node_owner(session, ...)` accepted a session, but
  `resolve_current_generation`, `generation_status` and `get_full_graph_for_repo`
  opened separate sessions. The export handed ORM nodes to its route after session
  close. Those were the application boundaries requiring changes under #335.

This is a source-level feasibility conclusion, not a live PostgreSQL concurrency
result. PostgreSQL's repeatable-read snapshot is established by the first data
statement and reused by later reads ([PostgreSQL 15 isolation documentation](https://www.postgresql.org/docs/15/transaction-iso.html#XACT-REPEATABLE-READ)).
SQLAlchemy supports per-transaction isolation configured before database work
([SQLAlchemy 1.4 transaction documentation](https://docs.sqlalchemy.org/en/14/orm/session_transaction.html#setting-isolation-for-individual-transactions)).
The implementation must verify effective isolation/read-only mode on its actual
connection and cleanup/pool behavior in local PostgreSQL tests. Long exports
retain row versions and connections; finite database/export deadlines must be
chosen and measured during implementation without silently truncating a graph.
If these checks invalidate this design, return for architectural review before
substituting locks, a composed SQL export, or staged storage.

## Loader, cache and request responsibilities

1. Retain cheap generation checks for warm-cache reuse. A usable check reports a
   coherent `repo_id`, completed identity and `ready` status from one read boundary;
   lookup errors, missing identity and non-ready states cannot authorize reuse.
   Lineage fields are not a certificate for a separately fetched graph.
2. On a cold load, mismatch or `force_reload`, pass the selected generation as
   `expected_generation_id`. Validate HTTP outcome, repository, explicit status,
   identity, count and graph shape **before** discarding metadata or building a
   usable graph. Export G must match the expectation and the cache label.
3. Missing/legacy identity, invalid envelope, 409, non-ready response or transport
   error produces no usable cache entry and no authoritative empty graph. Do not
   serve a previously cached A when the fresh check is unavailable or says B.
   Report unavailability/conflict explicitly to the caller.
4. Retain bounded LRU storage and synchronization. Each cache entry couples the
   validated graph with its own generation. In concurrent cold/forced loads an A
   completion must not relabel B data, or enable reuse of A after a fresh check
   selects B. Every subsequent invocation still performs the cheap check. Load
   coalescing and retaining multiple generations are not required.
5. Use a single validated materialized graph consistently within a structural
   operation. Direct TRACE/IMPACT results must expose `repo_id` and `ingestion_id`
   of that graph, and distinguish unavailability from a symbol absent at G.
6. A warm hit A authorized by a check at A can finish after B commits. This is
   snapshot consistency, not a guarantee of latest data at response time. Existing
   RAG/evidence outer generation fences must remain: generation drift across
   vector/graph/passage reads causes explicit retry/failure under their request
   contract. Do not remove these fences on the grounds that graph A is coherent.
   Graph correctness alone does not establish whole-request generation alignment.

## Compatibility and implementation boundary

Additive envelope fields and optional expectation do not make an old producer
compliant. New consumers fail closed on missing fields; no fallback to an
unidentified graph or independently assigned label is allowed. Publish producer
support first, then validating consumers, and verify both before claiming CI-01
closure. Old consumers remain outside the stronger guarantee during rollout.
No endpoint-version fork or legacy bypass is introduced by this contract.

No unresolved storage decision blocks this preferred design after source review.
Completed zero-node publication, historical graph retrieval, and request-wide
generation-fenced storage remain outside scope. If any becomes necessary, bring
that architectural decision to the owner before implementation. Runtime isolation,
transaction-duration limits and safe cancellation remain required verification
and operational work, not evidence already obtained.

## Required acceptance evidence for implementation

| Scenario | Required observation |
| --- | --- |
| Stable ready G, including no edges | Identity/status/content agree; exact node count; valid zero-edge graph |
| No nodes, completed attempt only; building, failed, missing owner request, deleted/unknown | Explicit non-ready outcome, null identity; never a ready empty graph or supported-looking absence |
| Newer attempt fails before replacing A | Completed owner A still exports A |
| Lookup A, export snapshot B | Expected A gets 409 if B ready, otherwise explicit unavailable; B is never cached as A |
| Rebuild/delete commits after owner read or between node/edge reads | Real PostgreSQL, deterministic barriers, surviving IDs with changed node/edge metadata: all A or explicit failure; never mixed or race-induced ready empty |
| Graph B committed, completion pending; completion occurs mid-read | Snapshot remains non-ready; next snapshot may see ready B |
| Writer rollback and superseded request cleanup during export | No partial publication; established A snapshot remains coherent or fails explicitly |
| Warm hit, force reload, concurrent cold loads | Cheap check avoids warm full fetch; each load validates its own identity; next call cannot bypass freshness checking |
| Missing identity, wrong repo/count/status, invalid shape, transport failure | Loader/cache composition rejects payload; no ready cache insertion or stale fallback |
| Direct structural APIs and RAG/evidence | Identity survives in structural responses; unavailable differs from absence; outer drift fences still reject whole-request drift |
| Timeout, exception, abandoned request and pooled connection reuse | Reader transaction releases promptly, pool returns to baseline; no isolation/read-only setting leaks into writers |

Use actual route/HTTP-client/loader/cache composition for the lookup/export race
and actual PostgreSQL transactions for database interleavings; mocks and sleeps
alone cannot establish isolation. Check effective isolation and materialization
boundaries, and include new database tests in CI selection. Synthetic probe and
older sequential tests are evidence of gaps, not acceptance of the future fix.
