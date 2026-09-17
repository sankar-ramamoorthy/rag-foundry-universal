---
title: "Documentation Index — rag-foundry-universal"
date: 2026-08-27
type: doc-index
status: complete
tags: [index, moc]
aliases: [Docs Index, DOCS MOC]
---

# Documentation Index

This routes to where the knowledge lives — it doesn't restate it. If a fact
here goes stale, fix the routing, not by copying content into this file.

## Status

[`DOCS/status.md`](/DOCS/status.md) is the single, continuously-updated
snapshot of what's currently shipped, in progress, and known-broken —
language/codebase-graph support, RAG quality evaluation results, and
known issues. `README.md` links here rather than embedding ADR/issue/PR
numbers itself. Not to be confused with `DOCS/log.md` (documentation-
structure governance) or `../status/` (an abandoned dated-snapshot
convention, see "Historical" below).

## Documentation Standard

New or substantially-edited docs follow
[the OKF documentation standard](/DOCS/standards/okf-documentation.md)
(frontmatter + linking conventions). [`DOCS/log.md`](/DOCS/log.md)
records documentation-standard-relevant history — new ADRs, policy
changes, structural migrations.

## Decisions

`DOCS/adr/` — check each ADR's own `status` field before relying on it;
don't assume numeric order implies currency.

[ADR-049: ingestion ownership and recovery](/DOCS/adr/ADR-049-ingestion-ownership-recovery.md)
records the accepted WP-R2 admission/recovery decision and its R3 boundaries.

[ADR-050: repository lifecycle consistency](/DOCS/adr/ADR-050-repository-lifecycle-consistency.md)
records the proposed WP-R3 repo-identity/generation-resolution/delete-lock
decision and its explicit non-goals (no zero-downtime staged publication).

## Audit & Planning

The active production-correctness programme is
[WP-R1 through WP-R8](/specs/005-production-correctness/spec.md), with
[delivery plan](/specs/005-production-correctness/plan.md),
[execution handoff](/specs/005-production-correctness/HANDOFF.md), and
[September 16 audit](/DOCS/audit/2026-09-16-repository-architecture-audit.md).
The [memory design review](/DOCS/audit/2026-09-16-bounded-ingestion-memory-design-review.md)
informs the amended [004 specification](/specs/004-bounded-ingestion-memory/spec.md).

Start at [[audit/00-Audit-Overview]] — the audit subtree's own index
(codebase findings, scalability/platform/LLM-provider plans, the roadmap,
and the RAG quality evaluation methodology).

[[audit/09-Retrieval-Technique-Decision-Gates]] — external retrieval/
generation ideas recorded as hypotheses with evidence-triggered decision
gates, not roadmap items; deliberately not linked from `07-Roadmap.md` or
`00-Audit-Overview.md`'s work-package index so an idea can't become
architecture just by being written down.

## Architecture Deep-Dives

`DOCS/architecture/` — diagrams and flow references (e.g. codebase ingestion
flow, repo query ASCII flow, extraction hierarchy model). Not yet
frontmatter-linked — planned follow-up.

## Deployment

`DOCS/deployment/` holds operational deployment guidance. Start with
[Production Docker Compose Release Process](/DOCS/deployment/production-docker-compose.md)
for the manual production release procedure, provenance checks, validation,
and rollback rules.

`DOCS/releases/` holds production release records. Current release:
[prod-2026-09-12](/DOCS/releases/2026-09-12-prod-release.md), deployed from
`202d91b34ee18e21c1dbb625d72acf9b82bce16d`. The earlier
[827c9cdc failed promotion](/DOCS/releases/2026-09-12-827c9cdc-failed-promotion.md)
is retained as part of the audit trail.

## Proposals

`DOCS/proposals/` — process/tooling proposals under discussion, not yet
binding: [[proposals/sdd-spec-kit-adoption]],
[[proposals/lean-instruction-routing-layer]] (before Phase 3).

## Evidence / Test Results

`DOCS/test_results/` — benchmark and verification records tied to specific
audit findings.

## Evaluations

`DOCS/evaluations/` — pre-registered evaluation question/candidate sets
(defined before the experiment runs, distinct from `DOCS/test_results/`'s
post-hoc verification evidence):
[[evaluations/2026-09-07-evidence-survival-question-set]].

## Patterns

`DOCS/patterns/` — reusable, framework-agnostic architecture patterns
worth taking to other projects (distinct from `DOCS/adr/`'s
this-repo decision records):
[Three-Layer Model/Provider Configuration](/DOCS/patterns/three-layer-model-config-pattern.md).

## Notes

`DOCS/notes/` — ad hoc working notes.

## Historical (non-authoritative)

`../docs-archive/`, `../status/` — do not treat as current source of truth.
[[../README_VISION|README_VISION.md]] — March 2026 external vision/design-intent
writeup, now annotated (2026-08-27) distinguishing what shipped from what's
still only envisioned; not a current-state reference.
