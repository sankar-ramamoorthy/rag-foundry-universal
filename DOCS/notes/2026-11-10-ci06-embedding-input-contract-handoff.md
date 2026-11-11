---
title: "CI-06 handoff: exact-input embedding contract, PR #339, what the owner decides next"
date: 2026-11-10
type: note
status: complete
summary: "PR #339 open after the independent review was resolved; not merged or deployed; ADR-056 proposed"
tags: [ci06, ci03, embedding, chunking, handoff]
related:
  - "[Issue #337](https://github.com/sankar-ramamoorthy/rag-foundry-universal/issues/337)"
  - "[PR #339](https://github.com/sankar-ramamoorthy/rag-foundry-universal/pull/339)"
  - "[ADR-056 (proposed)](/DOCS/adr/ADR-056-embedding-input-contract.md)"
  - "[CI-06 investigation](/DOCS/audit/2026-11-10-ci06-embedding-input-coverage-investigation.md)"
  - "[CI-06 verification](/DOCS/test_results/2026-11-10-ci06-embedding-input-coverage-verification.md)"
  - "[Independent review](/DOCS/audit/2026-11-10-ci06-pr339-independent-review.md)"
  - "[Final independent verification](/DOCS/audit/2026-11-11-ci06-pr339-final-verification.md)"
  - "[Supplied final assessment](/DOCS/notes/2026-11-11-ci06-final-review-assessment.md)"
  - "[Delivery evaluation protocol](/DOCS/evaluations/2026-11-10-ci06-delivery-evaluation-protocol.md)"
  - "[Implementation plan](/specs/005-production-correctness/ci06-plan.md)"
---

# CI-06 handoff (updated 2026-11-11)

Written so that anyone resuming CI-06 (a person, Claude Code or Codex) can do so
from the repository alone. Roadmap phase: Phase 6 correctness follow-up to the
November 10 audit.

## Where it stands

| Step | State | Evidence |
| --- | --- | --- |
| Issue | open (closes on merge) | #337 |
| Investigation and measurements | done, revised after review | [investigation](/DOCS/audit/2026-11-10-ci06-embedding-input-coverage-investigation.md), [verification](/DOCS/test_results/2026-11-10-ci06-embedding-input-coverage-verification.md) |
| Independent review R1–R5 | reproduced and resolved | [review](/DOCS/audit/2026-11-10-ci06-pr339-independent-review.md); verification "Review follow-up" |
| Delivery evaluation | pre-registered, all five criteria passed | [protocol](/DOCS/evaluations/2026-11-10-ci06-delivery-evaluation-protocol.md) |
| Decision record | **proposed** | [ADR-056](/DOCS/adr/ADR-056-embedding-input-contract.md) |
| Merge | **not done** | owner review of PR #339 |
| Deployment / clean rebuild | **not done** | operator-owned |

## Owner decisions

The [final Codex verification](/DOCS/audit/2026-11-11-ci06-pr339-final-verification.md)
recommends acceptance and merge at `770e3c9`, subject to current CI. The reporting
cleanup is recorded; the evaluation-cache issue remains a separate nonblocking
follow-up. No further architecture review cycle is recommended. This is a
recommendation, not a record of formal acceptance or merge.

1. Accept or amend ADR-056 at review.
2. Timing of the clean rebuild (decided 2026-11-11: rebuild existing indexes, no
   historical compatibility). Pinned E1 development and held-out generations
   change when rebuilt; finish or re-baseline in-flight comparisons first.
3. `vector_store_service` and `ingestion_service` must be deployed together.

## Practical notes for resuming

- Embedding experiments used the owner's remote Ollama (same
  `mxbai-embed-large` digest as local). Its address lives only in the
  git-ignored `.env` as `REMOTE_OLLAMA_BASE_URL`; never write it into tracked
  files. The live R1 test runs with `CI06_OLLAMA_URL` set.
- Raw captures and embedding caches are under `DOCS/test_results/_raw/ci06/`
  (git-ignored, deletable), indexed in
  [raw-index.json](/DOCS/test_results/raw-index.json). LightRAG and the two
  pinned foundry snapshots were checked out in a temporary directory; re-create
  them at `4d0afc1`, `109f12d8` and `3ba6a2f` to reproduce.
- Integration tests: `docker compose -f docker-compose.test.yml up -d postgres`,
  `alembic upgrade head` with `DATABASE_URL` on port 5433, then run
  `tests/api/test_incremental_ingest.py` from `ingestion_service` and
  `tests/core/vectorstore/test_retag_generation_fence.py` from
  `vector_store_service`.

## Related open work

- Evaluation-cache strict-validation provenance: final verification F1; the
  targeted provider check found zero rejections among 4,505 potentially affected
  upload passages. Tracked as #340.
- #313: the rest of CI-03 (extractor behavior, immutable model digest and
  inference configuration in the reuse identity).
- #338: uploaded Markdown / Docling section ingestion fails on `main` since #81;
  when fixed, sections should follow the ADR-056 contract.
- Passage size: 400-character windows looked better on needle discovery but were
  not evaluated for delivery.
