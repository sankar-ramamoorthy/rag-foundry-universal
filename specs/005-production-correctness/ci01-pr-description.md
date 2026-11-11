# CI-01: generation-bound graph exports and validated cache

## Change

Repository graph reads could resolve generation A, read nodes and edges across
later commits, and cache the graph under A without validating the export. CI-01
now materializes owner, completed status, nodes and relationships in one read-only
PostgreSQL repeatable-read transaction and returns its ingestion identity.
Expected-generation conflicts, explicit unavailable outcomes and validated cache
loads prevent mismatched or unidentified graphs from being served. Direct
TRACE/IMPACT identifies its snapshot; existing whole-request fences remain.

Refs #335 (Phase 6 CI-01, follow-up to #166/#168). Includes the owner-approved
contract and amended ADR-050/051. No storage migration, vector-generation filtering,
retrieval-policy change or deployment.

## Validation

- Actual PostgreSQL 15.15/pgvector 0.8.1: 28 CI-01 tests passed, including
  deterministic threaded rebuild/delete/cleanup barriers, completion timing,
  rollback, reused document IDs, transaction/pool settings, database timeout and
  abandoned ASGI-reader cleanup.
- Separate live producer/client processes verify lookup-A/export-B conflicts and
  unavailability, warm hits and forced loads. HTTP fixture tests cover invalid and
  legacy envelopes and concurrent loads.
- Expanded database regression: 57 passed. Ingestion units: 407 passed, 1 skipped.
  Orchestrator: 433 passed, 1 skipped. Root packaging: 202 passed.
- Ruff, private-address guard, whitespace and new documentation links passed.
  Focused Pyright: 0 errors. Whole-repository Pyright remains red (366 diagnostics);
  original `db_utils.py` has 23 diagnostics versus 20 here, with no added message.

Full commands, acceptance mapping and limitations:
`DOCS/test_results/2026-11-10-ci01-graph-snapshot-verification.md`.
Small controlled fixtures establish consistency, not scaling or answer quality.
Production deployment remains operator-owned; release producer support before
validating consumers. Remote CI and merge remain separate gates.

## README accuracy and documentation

- [x] README remains accurate: its lifecycle limitations still apply; API-specific
  changes are documented in the graph snapshot contract.
- [x] Progress and validation are recorded in `DOCS/status.md` and the evidence
  report; no development narrative was added to README.
- [x] New/modified local documentation links and the existing Apache-2.0 license
  declaration checked; no licensing change.
