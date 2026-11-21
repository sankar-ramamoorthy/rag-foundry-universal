---
title: "LAB / peri-Foundry boundary and the communication folder"
date: 2026-11-20
type: note
status: current
summary: "Working rules for any agent (Claude Code, Codex) in this repository: a separate agent project is a customer of Foundry's APIs; the only exchange channel is a sibling communication folder; no instructions either way; Foundry does not read the LAB directly."
tags: [lab, peri-foundry, communication-folder, boundaries, handoff]
related:
  - "[Evidence API assessment (#404)](/DOCS/notes/20261120-evidence-api-assessment-404.md)"
  - "[ADR-057 (proposed)](/DOCS/adr/ADR-057-react-typescript-product-frontend.md)"
---

# LAB / peri-Foundry boundary and the communication folder

Recorded 2026-11-20 at the owner's direction, so it survives a change of
agent (for example Claude Code to Codex). Knowledge lives here, not in any
agent's private memory.

## Context

A separate project, the LAB (the "peri-Foundry" investigation agent), is
being built in its own repository. It is a **customer of Foundry's evidence
APIs**. It supplies API requirements, not frontend or Foundry code, and its
own evaluation needs no UI. Foundry's order of work is: improve Foundry's
evidence capabilities first, then build the agent against them. All
Foundry implementation, including the React frontend, belongs in this
repository.

## Rules

1. **Exchange channel.** The folder `communication-folder`, a sibling of the
   directory that contains this repository's parent project folder under
   `dockerstuff`, is where Foundry and the LAB exchange information. The owner
   granted this repository's agents read-write access on 2026-11-20.
2. **No instructions either way.** Foundry does not post instructions or
   requests for the LAB there, and the LAB need not post instructions for
   Foundry. The folder carries information only: findings, contracts, status.
   Direction comes from the owner.
3. **No direct reads.** Foundry agents do not read the LAB repository
   directly. A direct listing attempt was denied by the tool classifier on
   2026-11-20 and must not be worked around. Use the communication folder,
   or material the owner relays.
4. **Governance is unchanged.** Issue before code, a roadmap phase on every
   issue, ADR for decisions, branch plus PR for everything.

## What has been exchanged

- The [evidence API assessment (#404)](/DOCS/notes/20261120-evidence-api-assessment-404.md)
  was copied to `communication-folder` as a finding. Decisions in it are
  addressed to the owner.
