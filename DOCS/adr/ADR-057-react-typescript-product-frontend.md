---
title: "ADR-057: React + TypeScript is the product frontend; Gradio stays during the transition"
date: 2026-11-20
type: adr
status: proposed
tags: [adr, frontend, react, typescript, gradio, product-identity, phase-6]
related:
  - "[WP-E6 product web UI](/DOCS/audit/05-Enterprise-Platform-Plan.md)"
  - "[Roadmap Phase 6](/DOCS/audit/07-Roadmap.md)"
  - "[Issue #402](https://github.com/sankar-ramamoorthy/rag-foundry-universal/issues/402)"
  - "[Issue #208](https://github.com/sankar-ramamoorthy/rag-foundry-universal/issues/208)"
  - "[Source navigation contract](/DOCS/architecture/source-navigation-api.md)"
---

# ADR-057: React + TypeScript product frontend

**Status: Proposed (2026-11-20).** Awaiting owner acceptance. No code, model
run or deployment is authorized by this record.

Roadmap phase: Phase 6 (repository, document, and coding-agent intelligence).

## Context

[WP-E6](/DOCS/audit/05-Enterprise-Platform-Plan.md) already named a React +
TypeScript SPA (Vite) as the eventual replacement for Gradio, and
[#208](https://github.com/sankar-ramamoorthy/rag-foundry-universal/issues/208)
deferred all UI work behind the foundation tranche. Gradio today is the only
interface and is the dev/demo surface for inventory, source navigation and
ordinary RAG.

The product direction under discussion is a code explorer built around four
capabilities: **Orient → Locate → Explain → Verify**. That presentation
(navigable sources, cited evidence, coverage and revision visible to the
user) is awkward to build in Gradio.

## Decision

1. **React + TypeScript is the chosen product interface.** The build tool is
   proposed as **Vite**; confirm it in the implementation plan, not here.
2. **All frontend implementation lives in `rag-foundry-universal`.** No other
   repository (including the evaluation LAB) modifies Foundry.
3. **The UI consumes stable, versioned APIs.** Repository intelligence,
   retrieval decisions and any agent reasoning stay in the services. The UI
   holds presentation state only and does not decide routing, evidence
   sufficiency or authorization.
4. **The transition is incremental.** Gradio stays operational until the
   React interface meets the agreed first-release requirements. Removing
   Gradio is a separate decision.

## Relationship to the parallel agent project

A separate agent project is a customer of Foundry's APIs. It does not change
this decision, but it fixes some boundaries:

- The frontend consumes Foundry-side APIs and is not coupled to any agent
  implementation. The agent's own evaluation depends on no UI, so React is
  not a prerequisite for measuring the first slice.
- The agent project supplies API requirements, not frontend code.
- Two prerequisites apply to any frontend, React or not: structured
  citations (file, range, revision) and a Foundry-side agent/question
  service to call.
- The key experience is a citation that opens the file and highlights the
  cited lines beside the conversation.
- No Gradio-specific chat interface should be built. This revises the
  earlier same-day Gradio-first stance, which predated the inspection.

Layout and timing are left to Foundry's own design process; nothing here is a
committed design.

## First slice (proposed definition)

Orient → Locate → Explain → Verify, as a presentation of capabilities that
already exist or are already planned. The first slice does not widen what the
product promises.

| Step | User-visible behavior | Existing backing capability (verify before implementing) |
| --- | --- | --- |
| Orient | Choose a repository; see its indexed revision/generation and overview | Repository lifecycle, orientation |
| Locate | Find a file or symbol and read bounded source | Source Navigation API |
| Explain | Ask a question; receive an answer with cited sources | Repository RAG endpoint |
| Verify | See the evidence behind the answer, revision, coverage and gaps | Provenance, final-context manifest |

First-release requirements and acceptance criteria are still to be agreed and
belong in a spec under `specs/`.

## Consequences

- Supersedes the "deferred, no implementation" stance of #208 **for the
  frontend only**; auth, gateway/TLS, team isolation and the rest of that
  issue's scope remain deferred.
- Needs an API assessment first: which existing endpoints are stable enough
  to consume, which are experimental, and which gaps (for example streaming)
  block the first slice. That assessment precedes any UI code.
- Adds a Node toolchain and a new container to the repository. CI, the
  Docker build context and the production compose file will need decisions of
  their own. Per [production deployment ownership](/DOCS/deployment/agent-execution-and-verification.md),
  deployment stays operator-owned.
- Two UIs coexist for a period. Gradio gets no new features beyond
  maintenance, to avoid building everything twice.

## Open questions

- Streaming answers: required for the first release, or later?
- Where the SPA is served (own container, behind a gateway, or by an
  existing service).
- Generated TypeScript client from the OpenAPI schemas versus hand-written.
- The exact first-release requirement list.
