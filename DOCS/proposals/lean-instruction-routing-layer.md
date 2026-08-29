---
title: "Proposal — Lean Multi-File Instruction Routing (CLAUDE.md / AGENTS.md / PROJECT.md)"
date: 2026-08-29
type: proposal
status: under discussion (not started)
horizon: before Phase 3 / WP-L1
tags:
  - proposal
  - process
  - documentation
  - agents
related:
  - "[[../index|DOCS index]]"
  - "[[../audit/07-Roadmap]]"
  - "[[../audit/03-Multi-Language-Graph-Plan]]"
  - "[[sdd-spec-kit-adoption]]"
---

# 🧭 Proposal — Lean Multi-File Instruction Routing

> [!warning] This is a hypothesis, not a decision
> Recorded at the user's request as a future planning note. No file has
> been added or restructured. The three-way split below (`PROJECT.md` /
> `AGENTS.md` / `CLAUDE.md`) is explicitly only a hypothesis about the
> final division of responsibility — inspect the current repository and
> this tool's actual instruction-loading behavior before deciding exact
> contents, don't assume the split below is correct as written. Do not
> begin implementation unless explicitly asked.

## 0 · Why this exists

`CLAUDE.md` is currently the single repository-instruction entry point.
That has worked so far, but two things are converging:

1. Phase 3 ([[../audit/03-Multi-Language-Graph-Plan]]) will substantially
   increase architectural and documentation complexity — tree-sitter
   extractors per language, the IR/GraphAssembler refactor, per-language
   ADRs and decision gates. A single entry-point file gets harder to keep
   both complete and lean as that complexity lands.
2. `CLAUDE.md` is Claude Code-specific. Other tools/agents that might
   touch this repo (or a human skimming for orientation) have no
   equivalent tool-neutral entry point today.

The question this proposal opens, not answers: should there be more than
one small entry-point file, each routing into the same canonical
documentation rather than each restating it?

## 1 · Desired principle

> small entry-point files → canonical indexed documentation → task-specific specs/evidence

None of `PROJECT.md`, `AGENTS.md`, or `CLAUDE.md` should duplicate
architecture descriptions, roadmap details, or rules that already live in
`DOCS/`, `DOCS/adr/`, `specs/`, or the current plan/proposal documents.
Where information can live canonically in `DOCS/`, it should not be copied
into an instruction file — only pointed to. This is the same discipline
`DOCS/index.md` already states for itself ("This routes to where the
knowledge lives — it doesn't restate it") extended to the instruction
layer above it.

## 2 · A hypothesis about the split (to investigate, not adopt as-is)

| File | Hypothesized scope |
|---|---|
| `PROJECT.md` | Tool-neutral project identity, current phase/status, canonical documentation entry points, high-level repository map. |
| `AGENTS.md` | Tool-neutral instructions for coding agents generally: workflow, issue/spec/PR discipline, testing expectations, where to find architecture and ADRs. |
| `CLAUDE.md` | Claude-specific operational guidance only, plus links into `PROJECT.md`, `AGENTS.md`, and the appropriate canonical docs. |

Open questions this proposal does not answer:

- Does splitting into three files actually reduce duplication risk, or
  does it just move the "three places can drift" problem one level up
  (now three entry-point files instead of one, each needing to stay in
  sync with the canonical docs and with each other)?
- What does this tool (Claude Code) actually load automatically today —
  only `CLAUDE.md`, or does it also pick up an `AGENTS.md`/`PROJECT.md` if
  present? This needs to be checked against actual harness behavior, not
  assumed, before committing to a split that depends on auto-loading
  working a particular way.
- Is a two-file split (e.g. `AGENTS.md` + tool-specific pointer files)
  sufficient, given `PROJECT.md`'s "identity/status/map" scope already
  overlaps significantly with `DOCS/index.md` and
  `DOCS/audit/00-Audit-Overview.md`'s dated status sections?

## 3 · Suggested timing

Before Phase 3 / `WP-L1`, per the roadmap
([[../audit/07-Roadmap#Phase 3 — Multi-language (4–6 weeks)|Phase 3]]) —
not now. The reasoning: Phase 3 is the point where documentation
complexity increases enough that a clean instruction-routing layer starts
paying for itself; doing this restructure earlier, against today's
simpler surface, would be solving a problem that doesn't exist yet.

## 4 · Non-goals

- Not a decision to add `AGENTS.md` or `PROJECT.md`.
- Not a decision about their exact contents — §2's table is a starting
  hypothesis for investigation, not a spec.
- Not an instruction to remove or shrink anything in `CLAUDE.md` today.
