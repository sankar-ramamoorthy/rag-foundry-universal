---
title: "Project Status"
date: 2026-09-14
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
- **Rust, Java** — not yet shipped (WP-L3/WP-L4 — planned, not started).
  See `DOCS/audit/03-Multi-Language-Graph-Plan.md` for the plan.
- **Retrieval `language` filter** on graph-aware queries — shipped
  (WP-L6a, issue #85), pulled forward ahead of WP-L3/L4 to validate
  WP-L2 against a real mixed-language repo.

## RAG quality

- The WP-Q0 baseline (issue #49; full evidence in
  [`DOCS/test_results/2026-08-27-wp-q0-rag-quality-baseline.md`](/DOCS/test_results/2026-08-27-wp-q0-rag-quality-baseline.md))
  measured 70%→90% Recall@5 from graph expansion over raw vector search
  alone. The reranker decision is **NO-GO**, evaluation-gated (see
  [`DOCS/audit/08-RAG-Quality-Evaluation-Methodology.md`](/DOCS/audit/08-RAG-Quality-Evaluation-Methodology.md)
  §4 for the reversal criterion).
- Follow-up retrieval-quality fixes and a second evaluation round
  (issues #64, #65, #79, #89, #91) are tracked in that same test-results
  doc and
  [`DOCS/test_results/2026-09-03-rag-retrieval-quality-linux-tailscale-baseline.md`](/DOCS/test_results/2026-09-03-rag-retrieval-quality-linux-tailscale-baseline.md).
  #91 (same-relation-type candidate overload) remains open.

## Known issues

- The NVIDIA NIM free-tier LLM provider is currently broken in the live
  deployment (issues #123, #124) — see
  [`DOCS/notes/20260913-free-provider-live-verification.md`](/DOCS/notes/20260913-free-provider-live-verification.md)
  for current per-provider status.

## Production release

- Current pinned deployment SHA and the audited-release history live
  under [`DOCS/releases/`](/DOCS/releases/) — not duplicated here.
