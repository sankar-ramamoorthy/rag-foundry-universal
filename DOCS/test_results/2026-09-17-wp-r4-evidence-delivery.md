---
title: "WP-R4 evidence-delivery implementation verification"
date: 2026-09-17
type: test-result
status: in-progress
tags: [retrieval, evidence, verification]
related:
  - "[WP-R4 specification](/specs/005-production-correctness/issues/evidence.md)"
  - "[ADR-052](/DOCS/adr/ADR-052-evidence-delivery-context-selection.md)"
  - "[Quality methodology](/DOCS/audit/08-RAG-Quality-Evaluation-Methodology.md)"
---

# WP-R4 verification checkpoint

Branch: `fix/wp-r4-evidence-delivery`.
Base: `3ba6a2f4cec4d3e0724859d70aeff98bb7f7880f`.
Results below were run against the uncommitted working tree; this is not a
pinned quality run or deployed-runtime claim.

## Executed checks

From `rag_orchestrator`, `../.venv/Scripts/python.exe -m pytest -q --tb=short`:
173 passed, 1 skipped (live model A/B environment not configured).

From `vector_store_service`, `../.venv/Scripts/python.exe -m pytest -m unit
-q --tb=short`: 28 passed, 13 deselected.

Root `.venv/Scripts/python.exe -m ruff check .`: passed.

Isolated `docker-compose.test.yml` PostgreSQL on localhost:5433, database
`ingestion_test`, migrated with root `python -m alembic upgrade head`:
`pytest tests/core/vectorstore/test_wp_r4_passages.py -q --tb=short` passed
(1 test). It writes and cleans up unique test identities, proves tail ordinal
97 ranks first among 100 passages, stable ordinal ties, generation/repository
filtering, ordinal-only fallback and sorted seed scores. Initial fixture
failures (missing artifact FK, UUID repository type and UUID/string comparison)
were corrected before this passing run; they were not product-query failures.
The new integration test is explicitly included in CI.

Focused pyright with `--pythonpath .venv/Scripts/python.exe` found two existing
environment/baseline issues: missing `sentence_transformers` and the vector
settings constructor's required `DATABASE_URL`. Full type-check success is
not claimed.

## Payload coverage

`test_wp_r4_payload.py` captures outgoing `/generate` JSON and checks seed tail
supplementation, same-relation overload, simple-document expansion, source /
manifest agreement, generation-change refusal and separate reranker loss.
`test_wp_r4_context.py` checks oversized-passage continuation and UTF-8/label/
separator accounting. These are deterministic mechanics tests using controlled
responses, not embedding or answer-quality evaluations.

## Outstanding acceptance

- Review complete query/prompt/output budget behavior and passage-level traces.
- Freeze and execute uncontaminated real-corpus questions with independent
  runtime/corpus/ground-truth revisions, baseline and matched-budget controls.
- Score clean/noisy generation, omissions/citations and stage attribution.
- Finish docs/status links, commit and push, inspect CI and deliver dedicated PR.
- Record deployment validation separately. Do not close #167 or claim quality
  completion based on this checkpoint.

## Owner-requested handoff

Checkpoint requested near the usage limit. Detailed live process/job state and
resume instructions are saved in [HANDOFF](/specs/005-production-correctness/HANDOFF.md).
The [quality protocol](/DOCS/evaluations/2026-09-17-wp-r4-protocol.md) and questions
are frozen, but no quality query or generation control has run. A source-only
corpus ingestion is active in a newly created isolated evaluation database.
