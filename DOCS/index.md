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

## Decisions

`DOCS/adr/` — check each ADR's own `status` field before relying on it;
don't assume numeric order implies currency.

## Audit & Planning

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

## Proposals

`DOCS/proposals/` — process/tooling proposals under discussion, not yet
binding: [[proposals/sdd-spec-kit-adoption]],
[[proposals/lean-instruction-routing-layer]] (before Phase 3).

## Evidence / Test Results

`DOCS/test_results/` — benchmark and verification records tied to specific
audit findings.

## Notes

`DOCS/notes/` — ad hoc working notes.

## Historical (non-authoritative)

`../docs-archive/`, `../status/` — do not treat as current source of truth.
[[../README_VISION|README_VISION.md]] — March 2026 external vision/design-intent
writeup, now annotated (2026-08-27) distinguishing what shipped from what's
still only envisioned; not a current-state reference.
