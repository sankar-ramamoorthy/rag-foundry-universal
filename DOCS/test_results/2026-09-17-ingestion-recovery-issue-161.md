---
title: "WP-R2 ingestion recovery and admission verification"
date: 2026-09-17
type: test-results
status: partial
tags: [ingestion, recovery, admission, postgres, acceptance]
related:
  - "[ADR-049](/DOCS/adr/ADR-049-ingestion-ownership-recovery.md)"
  - "[R2 acceptance and rollout](/specs/005-production-correctness/issues/recovery.md)"
  - "[Programme handoff](/specs/005-production-correctness/HANDOFF.md)"
---

# WP-R2 verification — #161 / draft PR #177

## Scope and current result

R2 is implemented on its branch, not yet merged or deployed. Code head 96952ce
passed all four checks in CI run 35269164566. Documentation follow-ups require
their own exact-head checks before merge. The owner is waiting to deploy;
no target Linux result is claimed.

## Evidence ledger

- Local file setup regression: three tests failed before the implementation,
  then passed after settings/pipeline/mark_running moved inside failure handling.
- Local full ingestion suite at 6347786: 304 passed, one skipped, 54 deselected.
  At 96952ce, 17 focused ownership/admission/setup tests pass. Repository lint
  and focused pyright for ownership/jobs/context pass. This is not a claim that
  all pre-existing repo-wide type errors were resolved.
- CI [35267843408](https://github.com/sankar-ramamoorthy/rag-foundry-universal/actions/runs/35267843408)
  found DBAPI access incompatibility: this SQLAlchemy runtime uses
  dbapi_connection, not driver_connection. Fixed in 6347786; not suppressed.
- CI [35268354926](https://github.com/sankar-ramamoorthy/rag-foundry-universal/actions/runs/35268354926)
  passed accepted/running hard-process-death tests and terminal-state protection.
  Admission correctly rejected an accepted row leaked by the earlier atomic
  graph fixture. Exact fixture cleanup added; no blanket database cleanup.
- CI [35268896379](https://github.com/sankar-ramamoorthy/rag-foundry-universal/actions/runs/35268896379)
  at cc4fd70 passed the ownership/process-death suite (eight tests), plus 11 of
  12 selected paging/HTTP tests, including the real vector-write kill test.
  Its only paging failure was the old parity test attempting completed -> running
  on one reused attempt. Corrected in 96952ce to create fresh attempts while
  retaining normalized output equality at buffers 1/7/128. Lint, all service
  unit suites, and synthetic memory acceptance passed in this run.

## Acceptance coverage

All four checks passed in
[35269164566](https://github.com/sankar-ramamoorthy/rag-foundry-universal/actions/runs/35269164566)
at 96952ce: lint, all service unit suites, PostgreSQL integration (including
fresh-attempt parity and real vector-write kill), and synthetic memory acceptance.

- A competing connection/process cannot reserve the single global slot while
  another owns it. Startup does not fail a live accepted owner.
- Kill a separate OS process at accepted and running stages: reconciliation
  writes failed/error/finished_at; progress survives; a repeated sweep is inert.
- Kill after two real HTTP batches (7 vectors each): all 14 acknowledged vectors
  remain visible from a fresh SQL session; status becomes failed and retained
  progress says 14. No Ollama/GPU inference is involved in this fixture.
- Terminate only the fixture's PostgreSQL lock-owning backend: a subsequent
  vector dispatch fails its guard before any HTTP POST. This does not cancel an
  already dispatched remote write or provide full distributed fencing.
- A stale SQLAlchemy identity-map instance cannot resurrect failed state or
  overwrite the original recovery error.
- Unmarked legacy active rows are untouched automatically and block admission;
  explicit stopped-worker reconciliation marks them failed.
- HTTP saturation returns 503/Retry-After; file route rejection does not invoke
  full file.read(). Unit injection covers preparation/commit/thread-launch
  failures and lock release; those unit tests alone do not prove DB durability.

## Remaining gates

Final exact-head green CI, final review, and PR merge remain. Target Linux
rollout requires the documented stop-old-workers procedure, then small
ingest/status/query smoke plus an isolated restart/recovery check. Record that
release evidence under #171. R3 deletion/rebuild consistency remains #166;
R2 must not be used to claim that partial corpora are safe to serve or mutate.
