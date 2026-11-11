---
title: "CI-01 generation-bound graph export: PostgreSQL verification"
date: 2026-11-10
type: test-result
status: complete
summary: "Local contract acceptance passed; repository-wide Pyright remains red; merge and deployment are separate"
source_commit: "562de0b plus the #335 implementation working tree"
tags: [ci01, graph, snapshot, postgresql, concurrency, cache]
related:
  - "[Issue #335](https://github.com/sankar-ramamoorthy/rag-foundry-universal/issues/335)"
  - "[Approved graph snapshot contract](/specs/005-production-correctness/contracts/repository-graph-snapshot.md)"
  - "[Implementation plan](/specs/005-production-correctness/ci01-plan.md)"
  - "[ADR-050](/DOCS/adr/ADR-050-repository-lifecycle-consistency.md)"
  - "[ADR-051](/DOCS/adr/ADR-051-generation-aware-graph-cache.md)"
  - "[Initial investigation](/DOCS/audit/2026-11-10-ci01-generation-snapshot-investigation.md)"
---

# CI-01 PostgreSQL verification — #335

The implementation passed the local CI-01 contract checks against **actual
PostgreSQL**, including concurrent reader/writer transactions and an actual
HTTP producer process consumed by the orchestrator's requests client, loader
and cache. No production or held-out corpus was accessed. No retrieval ranking,
vector-generation filter, canonical identity or storage-publication design changed.

## Environment and implementation

Windows host, root Python 3.12 environment, SQLAlchemy 1.4.54. A dedicated
`ci01-postgres-test` container used `pgvector/pgvector:pg15`, bound only to local
port 15435, with no host data mounts. The database was `ingestion_test`.
Observed server: PostgreSQL **15.15**, Debian x86_64 Linux; pgvector **0.8.1**.
All repository migrations were applied through `20261030_vc_idempotent_key`.

The export uses one fresh read-only repeatable-read transaction, with all selected
node/edge fields copied before rollback/close. The cheap generation endpoint uses
the same owner/status read boundary and includes lineage from it. Reader isolation
is set per connection/transaction; writer defaults remain unchanged. Connection
establishment is capped at five seconds on the existing service engine; the pool
retains its normal finite acquisition timeout. The export's configurable deadline
starts before acquisition and defaults to 60 seconds. Subsequent SQL phases use
the remaining budget for statement/idle-transaction timeouts, and materialization
checks the same monotonic deadline. The client uses connect/read timeouts of 5/70
seconds. These are failure bounds, not partial-export/truncation policies.

Ready exports identify `repo_id` and `ingestion_id`. Expected-generation conflicts
are 409; non-ready outcomes retain explicit status-bearing 200 envelopes. The loader
rejects unavailable, unidentified, malformed and mismatched payloads before graph
construction or caching. Direct TRACE/IMPACT returns the graph's ingestion identity;
symbol-not-found 404 details also identify the analyzed snapshot. Unavailable data
returns 503 instead of symbol absence. Existing RAG/evidence outer fences remain.

## Acceptance evidence

Primary tests:
[PostgreSQL/HTTP integration](/ingestion_service/tests/api/test_graph_snapshot_integration.py),
[consumer HTTP composition](/rag_orchestrator/tests/test_graph_snapshot_contract.py).

| Contract scenario | Actual verification |
| --- | --- |
| Ready G, expectation G, differing expectation and invalid UUID | Actual producer route returns identified G, 409 conflict without graph, and 422 respectively |
| Zero nodes, accepted/running/failed/completed attempt | Eight database cases distinguish unavailable from ready; a completed zero-node attempt is unknown |
| Ready graph with no edges; newer failed attempt without replacement | A remains ready, identified and valid with empty relationships |
| Rebuild, delete and superseded-request cleanup at owner and node/edge boundaries | Six threaded cases use `Event` barriers on actual SQL boundaries; writer commits before reader resumes; all nodes and edge metadata stay A |
| Reused document IDs | Rebuild tests assert document IDs are unchanged while node titles and relationship metadata become B in the next export |
| Completion commits after owner lookup | Established reader sees building; next snapshot sees completed B |
| Writer rollback | An open reader retains A across an uncommitted update/delete followed by rollback; subsequent export remains A |
| Effective transaction settings and pool reuse | PostgreSQL reports repeatable read / read only; success and injected failure return pool checkout count to baseline; subsequent writer reports read committed / read write / zero statement timeout and can publish |
| Database timeout | Actual `pg_sleep(1)` is interrupted by a 50 ms statement budget; reader releases its connection in under one second |
| Abandoned HTTP work | Cancel an ASGI request awaiting a real PostgreSQL reader sleeping for two seconds; its 100 ms database timeout terminates worker work and pool count returns to baseline |
| Lookup A / export ready B or building B | Separate live producer and orchestrator client processes; parent commits B between signalled lookup and released export; client gets 409 or 503, with no cache insertion |
| Actual HTTP warm/forced cache reads | Stable producer is fetched once on cold load, warm hit performs only the cheap check, force reload sends the expected generation and fetches again |
| Legacy/invalid envelope and unavailable/error outcomes | Fifteen HTTP fixture cases reject missing identity/status, wrong identity/repository/count, empty ready, malformed/duplicate nodes, malformed edges/metadata, non-ready states, conflict and server error |
| Concurrent cold/forced loads | Barrier-controlled HTTP fixture lets A finish after B; payload/label pairs stay correct and the next check selects/reloads B |
| Direct TRACE/IMPACT | Actual routes use the HTTP fixture-backed cache; successful and absent-at-snapshot results identify A; unavailable data is distinct from symbol absence |
| Existing request fences | Existing evidence-service and full orchestrator suites pass; no outer RAG/evidence generation fence was removed |
| Missing request / multiple owners | Missing request is tested at the resolver seam because healthy PostgreSQL FK prevents it; actual database multiple-owner corruption raises instead of selecting an arbitrary graph |

The threaded tests wait on explicit reader/writer barriers, not elapsed sleeps.
`pg_sleep` appears only in timeout/cancellation tests. Startup polling for the
isolated HTTP server is separate from concurrency scheduling. The historical
synthetic probe now reads its pinned `1a8fd587` source via `git show`, so its four
original gap demonstrations remain reproducible after the fix; it is not used
as proof of the new isolation behavior.

## Commands and results

Use the root environment as in CI. Before the database commands, set
`DATABASE_URL` to the isolated PostgreSQL URL on localhost:15435, database
`ingestion_test`. Do not point these fixture-writing tests at an existing corpus.

```powershell
# Repository root, with the isolated DATABASE_URL set:
.\.venv\Scripts\python.exe -m alembic upgrade head

# From ingestion_service:
..\.venv\Scripts\python.exe -m pytest tests/api/test_graph_snapshot_integration.py -q
..\.venv\Scripts\python.exe -m pytest tests/api/test_graph_snapshot_integration.py tests/api/test_repo_generation_integration.py tests/api/test_graph_export_relationship_metadata.py tests/core/test_repo_lifecycle.py tests/core/test_db_utils_repo_delete.py tests/codebase/test_atomic_graph_persistence.py -q
..\.venv\Scripts\python.exe -m pytest -m unit -q

# From rag_orchestrator:
..\.venv\Scripts\python.exe -m pytest -q

# Repository root:
.\.venv\Scripts\python.exe -m pytest tests/ --ignore=tests/test_code_evidence_prototypes.py -q
.\.venv\Scripts\ruff.exe check .
.\.venv\Scripts\python.exe scripts/check_private_addresses.py
git diff --check
```

| Run | Result |
| --- | --- |
| CI-01 PostgreSQL/HTTP suite, final run | **28 passed**, 27.56 s |
| Expanded database regression run | **57 passed**, 38.55 s |
| Ingestion unit suite | **407 passed**, 1 skipped, 126 deselected; 20.88 s |
| Full orchestrator suite | **433 passed**, 1 skipped; 18.13 s |
| Root packaging suite excluding the pre-existing unrelated untracked prototype test | **202 passed**, 12.13 s |
| Ruff, private-address guard, whitespace check | Passed |
| Historical pinned synthetic probe | All four original assertions passed |

Ingestion's skip is the pre-existing deferred CRUD integration test. The
orchestrator's skip is the opt-in live model A/B harness. Gradio warnings in the
ingestion suite concern empty repository lists and a moved theme parameter.
The database tests are explicitly included in the CI integration selection.

Focused Pyright (with `--pythonpath .venv/Scripts/python.exe`) passed for the
snapshot session helper, both new test modules, graph client/cache, structural
response models and routes: **0 errors / 0 warnings**. Repository-wide Pyright
remains red: the recorded full run reported **366 errors**. A temporary copy of
the original committed `db_utils.py`, checked with the same environment, reported
23 diagnostics versus 20 in the changed file, with **no added diagnostic kind or
message**. The new modules/tests have no focused diagnostics. The existing
Pydantic settings and SQLAlchemy model annotations are among the remaining
repository failures. This is not a clean whole-repository type-check claim, and
no repository-wide typing cleanup is included in #335.

## Limits and release boundary

This verifies the graph snapshot/cache contract on small controlled fixtures,
not large-export latency, memory scaling or answer quality. ASGI request
cancellation verifies worker/database cleanup; it does not claim every proxy or
OS-level disconnect instantly cancels Python work. Database statement/idle
timeouts and the materialization deadline bound reader lifetime even when an
HTTP waiter goes away. Pooled writer settings are separately verified.

No historical graph retrieval, completed zero-node publication, zero-downtime
staging, vector/passage snapshot transaction or request-wide generation storage
was added. Snapshot A can validly finish after B commits; whole-request drift
fences remain separate. No unresolved architectural change was needed to adopt
repeatable read. Producer support must be released before validating consumers;
old envelopes fail closed. CI/merge and operator-owned production deployment
remain separate from these local observations.
