---
title: "CI-06 handoff: exact-input embedding contract, PR #339, what the owner decides next"
date: 2026-11-10
type: note
status: complete
summary: "PR #339 open with green CI; not merged or deployed; ADR-056 proposed"
tags: [ci06, ci03, embedding, chunking, handoff]
related:
  - "[Issue #337](https://github.com/sankar-ramamoorthy/rag-foundry-universal/issues/337)"
  - "[PR #339](https://github.com/sankar-ramamoorthy/rag-foundry-universal/pull/339)"
  - "[ADR-056 (proposed)](/DOCS/adr/ADR-056-embedding-input-contract.md)"
  - "[CI-06 investigation](/DOCS/audit/2026-11-10-ci06-embedding-input-coverage-investigation.md)"
  - "[CI-06 verification](/DOCS/test_results/2026-11-10-ci06-embedding-input-coverage-verification.md)"
  - "[Implementation plan](/specs/005-production-correctness/ci06-plan.md)"
---

# CI-06 handoff (2026-11-10)

Written so that anyone resuming CI-06 (a person, Claude Code or Codex) can do so
from the repository alone. Roadmap phase: Phase 6 correctness follow-up to the
November 10 audit.

## Where it stands

| Step | State | Evidence |
| --- | --- | --- |
| Issue | open | #337 |
| Investigation and measurements | done | [investigation](/DOCS/audit/2026-11-10-ci06-embedding-input-coverage-investigation.md), [verification](/DOCS/test_results/2026-11-10-ci06-embedding-input-coverage-verification.md) |
| Decision record | **proposed**, not accepted | [ADR-056](/DOCS/adr/ADR-056-embedding-input-contract.md) |
| Implementation | on `fix/337-ci06-embedding-input-coverage` | PR #339, remote CI green, mergeable |
| Merge | **not done** | owner review |
| Deployment / re-ingestion | **not done** | operator-owned |

## Owner decisions before or at merge

1. Accept or amend ADR-056.
2. Rollout timing. The chunking and embedding version strings change, so the next
   ingestion of every repository re-embeds everything once. Pinned E1 development
   and held-out generations were built under the legacy contract; re-ingesting
   them changes their vectors and passages. Finish or re-baseline in-flight
   comparisons first.
3. Whether to run a delivery-side experiment on passage size. 400-character
   windows looked better on needle discovery but need about 1.8× the vectors, and
   passage caps downstream are counts, so delivered evidence per artifact would
   halve.

## Practical notes for resuming

- Embedding experiments ran on the owner's remote Ollama (same
  `mxbai-embed-large` digest as local; local CPU is several times slower). Its
  address lives only in the git-ignored `.env` as `REMOTE_OLLAMA_BASE_URL`; never
  write it into tracked files.
- Raw captures and embedding caches are under `DOCS/test_results/_raw/ci06/`
  (git-ignored, about 360 MB, deletable), indexed in
  [raw-index.json](/DOCS/test_results/raw-index.json). LightRAG was a shallow clone
  of the E1 pin `4d0afc1` in a temporary directory; re-clone it to reproduce.
- Integration tests: start `docker compose -f docker-compose.test.yml up -d postgres`,
  run `alembic upgrade head` with `DATABASE_URL` on port 5433, then run
  `tests/api/test_incremental_ingest.py` from `ingestion_service`.

## Related open work

- #313: the rest of CI-03 (extractor behavior and immutable model digest in the
  reuse identity).
- #338: uploaded Markdown / Docling section ingestion fails on `main` since #81;
  when fixed, sections should follow the ADR-056 contract.
