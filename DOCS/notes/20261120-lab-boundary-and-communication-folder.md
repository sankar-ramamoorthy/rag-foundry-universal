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

## Working agreement

Adopted 2026-11-21 at the owner's direction, from a draft the LAB agent
proposed. Both sides are meant to follow the same rules; the LAB keeps its own
record of them, and the owner settles any difference between the two records.

1. **Exchange channel.** `communication-folder` under `dockerstuff` is the
   only place Foundry and the LAB exchange material. Foundry's agents have
   read-write access (granted 2026-11-20).
2. **Foundry never reads the LAB repository.** Not directly, not by listing
   it. A direct listing attempt was denied by the tool classifier on
   2026-11-20 and must not be worked around. Foundry knows about the LAB only
   what is in the communication folder or what the owner relays. The owner has
   told the LAB the same. The LAB may read this repository.
3. **A file in the folder is information.** It becomes input to work only
   when the owner says "use X for Y". When it does, record the file's SHA-256
   as read and what it was used for. Do not copy LAB material into this
   repository unless the owner says to: the repository is public and the LAB's
   drafts may change.
4. **Writes happen only when the owner asks.** Neither side posts instructions
   or requests for the other. The owner may ask either side to write or accept
   something specifically, and may give a standing ask so the owner is not the
   bottleneck (for example, "post a one-paragraph status note when a
   deliverable the other side depends on is done"). Absent an ask, do not
   write. Information flows both ways; direction comes only from the owner.
5. **List the folder** at the start of a session, and again before
   reporting that work is blocked on the owner or on the other side.
6. **Factual disagreements are settled against source.** Each side corrects
   its own record and reports the correction as information, not as a request.
7. **Governance is unchanged.** Issue before code, a roadmap phase on every
   issue, ADR for decisions, branch plus PR for everything.

## What has been exchanged

- The [evidence API assessment (#404)](/DOCS/notes/20261120-evidence-api-assessment-404.md)
  was copied to `communication-folder` as a finding. Decisions in it are
  addressed to the owner.
- The LAB's Mealie development questions were read from the folder for #409 on
  the owner's instruction (SHA-256 recorded on that issue). They were not
  copied here.
