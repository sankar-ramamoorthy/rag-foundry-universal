---
title: "Project Status"
date: 2026-09-16
type: status
status: current
tags: [status, overview]
related:
  - "[Documentation Index](/DOCS/index.md)"
  - "[Multi-Language Graph Plan](/DOCS/audit/03-Multi-Language-Graph-Plan.md)"
  - "[Audit Overview](/DOCS/audit/00-Audit-Overview.md)"
---

# Project Status

Single evolving snapshot of what's currently shipped, in progress, and
known-broken. **Update this file in place** on substantial changes —
don't create a dated copy of it (that's the abandoned `status/`
directory convention; see `DOCS/index.md`'s "Historical" section) and
don't confuse it with [`DOCS/log.md`](/DOCS/log.md), which tracks
documentation-*structure* governance changes, not feature/project status.

This is where ADR/issue/PR-numbered detail belongs — `README.md` links
here rather than embedding it, so the README stays a stable reference
document.

## Language / codebase graph support

- **Python** — tree-sitter-based extraction, the production default
  since WP-L5 (issue #134, [PR #135](https://github.com/sankar-ramamoorthy/rag-foundry-universal/pull/135)).
  The legacy stdlib-`ast` extractor is retained as an automatic + manual
  rollback path (`PYTHON_TREESITTER_ENABLED` /
  `PYTHON_TREESITTER_AUTO_FALLBACK` env vars); see the WP-L5 section of
  [`DOCS/audit/03-Multi-Language-Graph-Plan.md`](/DOCS/audit/03-Multi-Language-Graph-Plan.md)
  for the rollback mechanism and parity evidence.
- **TypeScript / JavaScript** — tree-sitter-based extraction, shipped
  (WP-L2, issue #83).
- **Rust** — tree-sitter-based extraction, shipped (WP-L3, issue #130,
  [PR #131](https://github.com/sankar-ramamoorthy/rag-foundry-universal/pull/131)).
- **Java** — tree-sitter-based extraction, shipped (WP-L4, issue #132,
  [PR #133](https://github.com/sankar-ramamoorthy/rag-foundry-universal/pull/133)).
- **Retrieval `language` filter** on graph-aware queries — shipped
  (WP-L6a, issue #85), pulled forward ahead of WP-L3/L4 to validate
  WP-L2 against a real mixed-language repo.

## RAG quality

- The WP-Q0 baseline (issue #49; full evidence in
  [`DOCS/test_results/2026-08-27-wp-q0-rag-quality-baseline.md`](/DOCS/test_results/2026-08-27-wp-q0-rag-quality-baseline.md))
  measured 70%→90% Recall@5 from graph expansion over raw vector search
  alone.
- Follow-up retrieval-quality fixes and a second evaluation round
  (issues #64, #65, #79, #89, #91) are tracked in that same test-results
  doc and
  [`DOCS/test_results/2026-09-03-rag-retrieval-quality-linux-tailscale-baseline.md`](/DOCS/test_results/2026-09-03-rag-retrieval-quality-linux-tailscale-baseline.md).
  #91 (same-relation-type candidate overload) remains open.
- **Doc-type-aware seed tie-break** (issue #142, fix for #141): a
  self-ingested Markdown eval doc's near-verbatim question text could
  outrank the real implementation it discussed badly enough to exclude
  it from the seed search's `top_k` entirely. Fix is merged, flag-gated
  off by default (`DOC_TYPE_TIE_BREAK_ENABLED`) — live re-verification
  on 2026-09-15 found the original repro no longer reproduces post
  corpus drift, so this stays `investigate`, not `validated`; see
  [`DOCS/test_results/2026-09-14-doc-type-tie-break-issue-141.md`](/DOCS/test_results/2026-09-14-doc-type-tie-break-issue-141.md).
- **HNSW post-filter under-recall** (issue #150): a `repo_id`-filtered
  vector search could silently return far fewer rows than requested
  (confirmed capped at ~28 regardless of `LIMIT`, once the shared
  multi-repo `vector_chunks` index made the filter selective enough).
  Fixed via pgvector iterative index scans
  (`hnsw.iterative_scan=relaxed_order` + `max_scan_tuples=20000`),
  restoring full recall at ~17-24ms — see
  [`DOCS/test_results/2026-09-15-hnsw-iterative-scan-issue-150.md`](/DOCS/test_results/2026-09-15-hnsw-iterative-scan-issue-150.md).
- **Optional cross-encoder reranker** (WP-S8, issue #152): implemented,
  flag-gated off by default (`RERANK_ENABLED`), request-overridable
  (`RAGQuery.rerank`/`SimpleRAGQuery.rerank`) for A/B comparison without
  a redeploy. Built deliberately *ahead of* the reranker decision gate's
  own evaluation requirement — see
  [`DOCS/notes/20260915-reranker-built-ahead-of-evaluation-gate-decision.md`](/DOCS/notes/20260915-reranker-built-ahead-of-evaluation-gate-decision.md)
  for why. **Plumbing exercised live; quality benefit remains unvalidated** —
  the [September 15 run](/DOCS/test_results/2026-09-15-wp-s8-rerank-evidence-survival-run.md)
  was contaminated and had insufficient clean cases. The reranker decision in
  [`DOCS/audit/09-Retrieval-Technique-Decision-Gates.md`](/DOCS/audit/09-Retrieval-Technique-Decision-Gates.md)
  stays `deferred/NO-GO` as a *default* pending clean, pinned, matched-budget
  comparisons accounting for issue #150's recall fix.

## Known issues

- The [September 16 architecture audit](/DOCS/audit/2026-09-16-repository-architecture-audit.md)
  identifies production blockers now tracked as
  [WP-R1–R8](/specs/005-production-correctness/spec.md): #160 memory, #161
  recovery/admission, #166 corpus lifecycle, #167 evidence delivery, #168
  snapshot/cache freshness, #169 health/provenance, #170 blocking I/O, and
  #171 current-release verification. At programme creation, these fixes are
  **planned, not implemented or production validated**. Execution state is in
  the [handoff](/specs/005-production-correctness/HANDOFF.md).
  Planning PR #164 is merged. WP-R6/#169 healthcheck and runtime-provenance
  implementation has [local verification evidence](/DOCS/test_results/2026-09-16-healthchecks-provenance-issue-169.md);
  PR #172 is merged with green CI; Linux validation remains pending.
  #160 has an integrated worker merged in PR #175 with
  [unit/real HTTP and PostgreSQL evidence](/DOCS/test_results/2026-09-17-bounded-ingestion-issue-160.md);
  synthetic Linux RSS and graph/vector parity passed; pinned DocsGPT and
  admission/mutation gates remain open. R2/#161 (ownership/admission/recovery)
  is merged to main via PR #177 (`12cf75d`), with real-PostgreSQL/process-kill
  CI evidence, [recovery/admission tasks and rollout](/specs/005-production-correctness/issues/recovery.md)
  and [accepted ADR-049](/DOCS/adr/ADR-049-ingestion-ownership-recovery.md).
  Linux/live rollout validation remains a separate, still-pending #171 gate;
  do not treat merged CI as production deployment. Other fixes remain planned.
  September 17 follow-up #176 tracks intermittent zero ANN results after bulk
  deletion in CI; production impact and exact cause remain unverified.

- The NVIDIA NIM free-tier LLM provider is currently broken in the live
  deployment (issues #123, #124) — see
  [`DOCS/notes/20260913-free-provider-live-verification.md`](/DOCS/notes/20260913-free-provider-live-verification.md)
  for current per-provider status.

## Production release

- Current pinned deployment SHA and the audited-release history live
  under [`DOCS/releases/`](/DOCS/releases/) — not duplicated here.
