# WP-R2: ingestion ownership, recovery and admission

Tracking issue: [#161](https://github.com/sankar-ramamoorthy/rag-foundry-universal/issues/161)
Status: Implemented and CI-validated on PR #177; merge pending final review.
Linux/live deployment validation remains a separate #171 gate, not claimed here.
Contract: [programme specification](../spec.md#recoveryadmission-contract-161)
Related: [R3 lifecycle](./lifecycle.md), [R1 tasks](../../004-bounded-ingestion-memory/tasks.md)

## Scope

Both file and repository ingestion must reserve capacity before full file reads
or cloning. Return a retryable HTTP response on saturation, with no accepted
request left behind. Bound active accepted/running work across service processes,
not merely within each Python process. No durable queue or automatic retry.

Every accepted request needs ownership acquired before its row becomes visible,
including the interval before its thread starts. A hard process death must be
reconciled to failed with an explanatory error and finished_at. Preserve partial
graph/vector data and progress. A second server starting must not fail live jobs.
Recovery must recheck status under the ownership guard before changing it.

## Design review requirements

The intended implementation direction is PostgreSQL-backed ownership shared
by admission and recovery, with a reusable repository-mutation guard for R3.
Before finalizing the implementation/ADR, resolve these failure cases explicitly:

- Ownership acquired before request commit; released only after terminal state
  or a failed launch is recorded. No gap between HTTP acceptance and worker start.
- Lock connection cleanup must not return held session locks to a connection pool.
- Database connection loss is not proof the Python worker stopped. Specify
  fail-closed behavior and stale-worker write protection; do not claim a lock
  alone fences HTTP writes made through another service.
- Old accepted/running rows have no ownership record. Do not misclassify live
  old-version workers during mixed-version rollout. Provide an explicit stopped-
  old-workers migration/reconciliation procedure for historical rows.
- Recovery must also work when one worker dies while another service process
  remains alive; startup-only handling needs a subsequent trigger or sweep.
- Admission settings must have consistent database-wide semantics across workers.
- No long database transaction should span clone/embed/HTTP calls.
- Multipart spooling can precede the endpoint; admission before file.file.read()
  bounds application ingestion, not all ingress disk/network resource use.

ADR-030/031 identity remains unchanged. Existing ADR-038 factory drift (#165)
is disclosed and not repaired incidentally by this work.

## Acceptance tasks

- [x] Reproduce settings/pipeline/mark_running exceptions before the file worker
  failure handler; move setup into handler; three focused unit regressions pass.
- [x] Finalize ownership/admission/recovery design and issue-linked ADR
  (ADR-049, status: accepted).
- [x] Implement common ownership primitive and tests before route integration.
- [x] Integrate both entrypoints; handle upload-read, request-commit and thread-
  launch failures; release capacity on every terminal path. (`submit_ingestion`
  wired into `ingest.py` and `codebase_ingest.py`.)
- [x] Implement recovery startup/ongoing trigger and legacy rollout handling.
  (`reconcile_ingestions` on startup + 5-second sweep in `main.py`;
  `scripts/reconcile_ingestions.py` for the explicit stopped-old-workers case.)
- [x] Real PostgreSQL, separate processes: live owner survives competing startup;
  kill after acceptance/before launch and after acknowledged vector writes;
  recovery persists failed/error/timestamp/progress in fresh sessions.
  (CI run 35269164566 at 96952ce/bc17e46.)
- [x] Concurrent admission proves global capacity; saturation does not read the
  full upload, clone, create accepted rows or launch workers.
- [x] Verify connection-loss and late-completion races; failed cannot resurrect.
- [x] Keep R3 delete/ingest exclusion explicitly pending unless implemented and
  verified together; do not equate R2 admission with full corpus consistency.
  (Confirmed still separate; no R3 work folded in here.)
- [x] Service suites, lint, relevant types, real CI; record evidence and KB links.
  (See [evidence ledger](/DOCS/test_results/2026-09-17-ingestion-recovery-issue-161.md).)
- [x] Commit/push dedicated PR, inspect exact-head CI, merge; record Linux gates.
  (PR #177; Linux rollout evidence remains a separate #171 gate, not claimed here.)

## Current evidence

September 17: tests/api/test_ingestion_recovery.py failed all three cases against
the merged R1 code, then passed after moving file setup/mark_running into its
existing try/except. These are mocked status-write regressions, not hard-kill,
database durability, admission or recovery acceptance evidence.

Initial primitive added: detached PostgreSQL session locks, one database-wide
slot shared by all ingestion entrypoints (no replica-local capacity setting),
attempt lock held before accepted-row creation, managed metadata marker, paged
reconciliation and explicit include_legacy maintenance option. Not yet wired
into routes/startup. Status writes now lock/refresh the row and reject terminal
resurrection. Local ingestion unit suite: 295 passed, 1 skipped; seven focused
R2 tests pass. Real PostgreSQL/process-death tests added to CI, not yet executed.

Outstanding design boundary: ownership loss can interrupt a still-alive Python
worker; it must stop at subsequent work boundaries, and terminal writes must
not resurrect it. A vector HTTP request already in flight can finish, leaving
partial data. R2 does not automatically retry/delete that data. Full same-repo
write fencing and replacement/delete consistency remain R3; do not claim that
the advisory primitive alone implements them.

## Rollout

Deployment is deferred until the R2 PR is merged and its exact-head checks pass.
Use the current release's Compose files/env arguments for every command below.
Back up data worth retaining. Stop ALL old ingestion containers/processes using
this database; do not do a mixed-version rolling deployment. Keep Postgres up.
Build/pull the reviewed new ingestion image before running the one-off command.

```bash
docker compose stop ingestion_service
docker compose run --rm --no-deps ingestion_service uv run --directory /app/ingestion_service python -m src.core.ingestion_ownership --confirm-old-workers-stopped
docker compose up -d ingestion_service
```

The bare Compose command is illustrative: preserve production override/env-file
arguments from the existing release runbook. The explicit confirmation authorizes
marking legacy accepted/running rows failed, not deleting any artifacts or vectors.
It cannot prove old workers are stopped; the operator must verify that first.
The script wrapper `scripts/reconcile_ingestions.py` provides the same operation
from a checkout with the ingestion dependencies/environment configured.

After startup verify health/version and the status of any pre-existing interrupted
attempt. Run a small isolated ingestion, send a second while it is active (expect
503 + Retry-After), verify completed/query behavior. In an isolated fixture only,
kill the ingestion process, restart, and verify failed/error/finished_at plus
retained partial writes. Do not expect automatic retry/resume or cleanup.
Avoid concurrent delete/re-ingest until R3. Record Linux evidence in #171.
