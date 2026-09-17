# WP-R2: ingestion ownership, recovery and admission

Tracking issue: [#161](https://github.com/sankar-ramamoorthy/rag-foundry-universal/issues/161)
Status: In progress; not deployment-ready.
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
- [ ] Finalize ownership/admission/recovery design and issue-linked ADR.
- [ ] Implement common ownership primitive and tests before route integration.
- [ ] Integrate both entrypoints; handle upload-read, request-commit and thread-
  launch failures; release capacity on every terminal path.
- [ ] Implement recovery startup/ongoing trigger and legacy rollout handling.
- [ ] Real PostgreSQL, separate processes: live owner survives competing startup;
  kill after acceptance/before launch and after acknowledged vector writes;
  recovery persists failed/error/timestamp/progress in fresh sessions.
- [ ] Concurrent admission proves global capacity; saturation does not read the
  full upload, clone, create accepted rows or launch workers.
- [ ] Verify connection-loss and late-completion races; failed cannot resurrect.
- [ ] Keep R3 delete/ingest exclusion explicitly pending unless implemented and
  verified together; do not equate R2 admission with full corpus consistency.
- [ ] Service suites, lint, relevant types, real CI; record evidence and KB links.
- [ ] Commit/push dedicated PR, inspect exact-head CI, merge; record Linux gates.

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
