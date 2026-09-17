---
title: "ADR-049: Ingestion admission and database-session ownership"
date: 2026-09-17
type: adr
status: accepted
tags: [ingestion, lifecycle, recovery, concurrency]
related:
  - "[WP-R2 specification](/specs/005-production-correctness/issues/recovery.md)"
  - "[WP-R3 lifecycle](/specs/005-production-correctness/issues/lifecycle.md)"
  - "[ADR-030](/DOCS/adr/ADR-030-unified-artifact-graph.md)"
  - "[ADR-038](/DOCS/adr/ADR-038-pipeline-construction-ownership.md)"
---

# ADR-049: Ingestion admission and database-session ownership

Tracking: #161 / WP-R2, PR #177. Accepted: implemented, real-PostgreSQL
CI-validated (run 35269164566 at 96952ce/bc17e46); Linux rollout evidence
remains a separate #171 gate, not covered by this ADR's acceptance.

## Decision

Use one PostgreSQL session-level admission lock for all file/repository
ingestions across API processes sharing the database. This deliberately limits
the present single-GPU installation to one active ingestion, including upload
materialization and worker setup. Saturation returns 503 with Retry-After: 5;
there is no in-memory backlog. Multipart spooling before endpoint invocation
is outside this bound. Replica-local configurable limits are not introduced.

Acquire an attempt lock before committing accepted state. Hold both locks on
one detached DBAPI connection, transferring it once from the accepting request
to its worker. Use autocommit on the lock connection: no long transaction spans
clone, extraction, embedding or HTTP. Close physically rather than returning
session locks to a pool. Lock namespaces distinguish admission/attempt and can
support the repository mutation guard in R3; R3 must cover deletion too.

Ownership metadata is server-generated, replacing any supplied reserved marker.
No schema migration is needed. Startup, a five-second sweep, and admission
reconcile active managed rows whose attempt lock is available. Recovery takes
the attempt lock and locks/rechecks the request row, then writes failed,
finished_at and a reason while preserving progress and partial data. No job-age
heuristic, automatic retry, deletion or resume is implied.

Status mutations lock and refresh the row; failed/completed cannot become
running/completed again. A worker error cannot overwrite the first terminal
reason. Settings/pipeline construction, upload preparation and thread-launch
errors are inside the lifecycle handling.

## Failure boundaries

A released lock proves loss of database ownership, not necessarily OS process
death. The failure reason says ownership is absent. Workers check their original
connection at status, graph-commit, embedding and vector-dispatch boundaries;
they never reconnect that guard. Recovery does not intentionally kill a process.
Already-dispatched HTTP writes can finish and extraction may continue until a
check boundary. Those partial effects are retained, not mistaken for completion.

This is NOT distributed write fencing or full corpus lifecycle consistency.
After database-session failure, a paused worker and an in-flight remote write
require the R3 same-repository mutation/publication contract before unrestricted
rollout. R2's global admission bound applies while database ownership is intact;
it is not an OS CPU/memory quota for suspended or disconnected work.

The graph builder is still unbounded; one-job admission is not a whole-process
memory bound. File summary dispatch currently holds the slot until return, even
after completed state. This favors bounded work over admission throughput.

## Legacy rollout

Old active rows have no reliable owner marker. Automatic recovery leaves them
alone, and admission conservatively rejects new jobs while they remain active.
Stop every old-version worker connected to the database before invoking explicit
legacy reconciliation. The operator command requires
`--confirm-old-workers-stopped`; it does not verify that assertion remotely.
Do not roll old and new ingestion workers concurrently.

See [R2 rollout](/specs/005-production-correctness/issues/recovery.md#rollout).

## Alternatives and constraints

Unconditionally failing running rows at startup would fail another live worker.
An age-only timeout would mistake a large ingestion for a dead owner. A local
semaphore would multiply capacity across processes. A durable queue is a later
architecture change; current work needs bounded execution and truthful failure.
Existing pipeline factory drift (#165) remains disclosed, not silently fixed.

## Verification required

Real PostgreSQL tests must prove competing-owner protection, global admission,
terminal-state monotonicity, legacy safety, and recovery after an OS process kill.
Separate real vector HTTP testing must prove acknowledged partial writes survive.
HTTP tests verify 503/Retry-After and no upload read after saturation. Local
mock tests alone cannot accept this decision. Target Linux release evidence is
tracked separately in #171; R3 consistency remains #166.
