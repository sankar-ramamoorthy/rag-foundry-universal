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

## Architecture Deep-Dives

`DOCS/architecture/` — diagrams and flow references (e.g. codebase ingestion
flow, repo query ASCII flow, extraction hierarchy model). Not yet
frontmatter-linked — planned follow-up.

## Proposals

[[proposals/sdd-spec-kit-adoption]] — process/tooling proposals under
discussion, not yet binding.

## Evidence / Test Results

`DOCS/test_results/` — benchmark and verification records tied to specific
audit findings.

## Notes

`DOCS/notes/` — ad hoc working notes.

## Historical (non-authoritative)

`../docs-archive/`, `../status/` — do not treat as current source of truth.
