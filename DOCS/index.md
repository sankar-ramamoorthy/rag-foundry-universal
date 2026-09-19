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
structure governance) or the old top-level `status/` directory (an
abandoned dated-snapshot convention, archived 2026-09-18 — see
"Historical" below).

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
records the accepted WP-R3 repo-identity/generation-resolution/delete-lock
decision and its explicit non-goals (no zero-downtime staged publication).

[ADR-051: generation-aware graph cache](/DOCS/adr/ADR-051-generation-aware-graph-cache.md)
records the accepted WP-R5 (narrowed #168) decision keying
`rag_orchestrator`'s graph cache on `(repo_id, generation_id)` with LRU
bounding, and its explicit non-goals (no vector-store generation filtering,
no live two-service HTTP round-trip test yet).

## Audit & Planning

The production-correctness programme
([WP-R1 through WP-R8](/specs/005-production-correctness/spec.md), with
[delivery plan](/specs/005-production-correctness/plan.md),
[execution handoff](/specs/005-production-correctness/HANDOFF.md), and
[September 16 audit](/DOCS/audit/2026-09-16-repository-architecture-audit.md))
is substantially closed as of WP-R4/#167 (2026-09-18). The
[memory design review](/DOCS/audit/2026-09-16-bounded-ingestion-memory-design-review.md)
informs the amended [004 specification](/specs/004-bounded-ingestion-memory/spec.md).

The active next tranche is **Phase 6** in
[`07-Roadmap.md`](/DOCS/audit/07-Roadmap.md#phase-6--repository-intelligence-and-incremental-ingestion-foundation) —
13 prioritized issues (#196-#208) covering incremental ingestion/snapshot
lineage, repository intelligence (ORIENT/TRACE/IMPACT), provenance/source
authority, and related foundation work. Items 1-3 (#196, #197, #198) and
their fast-follows (#216, #220, #221) have shipped. Next is #200 (bounded
evidence sufficiency), followed by #199 (source authority / subject /
provenance), then authority/provenance-aware sufficiency checks.

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

The [Phase 6 Claude handoff](/DOCS/proposals/2026-09-19-phase-6-sufficiency-authority-handoff.md)
plans #200 mechanical sufficiency, then #199 authority/subject/provenance, then
authority-aware sufficiency checks. Its
[code findings](/DOCS/notes/2026-09-19-phase-6-sufficiency-findings.md)
record the inspected baseline and implementation seams. This is proposed work,
not a shipped capability.

`DOCS/proposals/` — process/tooling proposals under discussion, not yet
binding: [[proposals/sdd-spec-kit-adoption]],
[[proposals/lean-instruction-routing-layer]] (before Phase 3).

## Evidence / Test Results

[WP-R4 evidence delivery](/DOCS/test_results/2026-09-17-wp-r4-evidence-delivery.md)
tracks local mechanics verification and outstanding quality gates;
[ADR-052](/DOCS/adr/ADR-052-evidence-delivery-context-selection.md) records the accepted contract.



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

`../docs-archive/` — do not treat as current source of truth, including
its `status-snapshots-2025-2026/` subdirectory (dated pre-rename project
notes, formerly a top-level `status/` directory — consolidated 2026-09-18
since it had been untouched since the repository's first commit and
duplicated `DOCS/status.md`'s purpose).
[[../README_VISION|README_VISION.md]] — March 2026 external vision/design-intent
writeup, now annotated (2026-08-27) distinguishing what shipped from what's
still only envisioned; not a current-state reference.

For **current** project status, see [`status.md`](/DOCS/status.md) above
this section — it's the single, continuously-updated status document;
nothing else in the repo should be treated as an alternative to it.
