# Implementation Plan: [FEATURE]

**Branch**: `[###-feature-name]` | **Date**: [DATE] | **Spec**: [link]

**Tracking Issue**: #[ISSUE_NUMBER]

**Roadmap Context**: [Phase / WP if applicable]

**Input**: Feature specification from `/specs/[###-feature-name]/spec.md`

**Note**: This template is filled in by the `/speckit-plan` command; its definition describes the execution workflow.

## Summary

[Extract from feature spec: primary requirement + technical approach from research]

## Technical Context

<!--
  ACTION REQUIRED: Replace the content in this section with the technical details
  for the project. The structure here is presented in advisory capacity to guide
  the iteration process. Populate only fields relevant to this feature. Use
  `N/A — <reason>` where a field genuinely does not apply. Do not invent
  requirements to fill the template.

  Claims about the existing architecture MUST be verified against current
  code/configuration. Audit documents, DeepWiki, CLAUDE.md, and prior
  discussions may guide investigation but are not substitutes for live-code
  verification (Constitution Governance: amendments/claims require the same
  verification discipline used to ratify the constitution itself).
-->

**Language/Version**: [e.g., Python 3.11, Swift 5.9, Rust 1.75 or NEEDS CLARIFICATION]

**Primary Dependencies**: [e.g., FastAPI, UIKit, LLVM or NEEDS CLARIFICATION]

**Storage**: [if applicable, e.g., PostgreSQL, CoreData, files or N/A]

**Testing**: [e.g., pytest, XCTest, cargo test or NEEDS CLARIFICATION]

**Target Platform**: [e.g., Linux server, iOS 15+, WASM or NEEDS CLARIFICATION]

**Project Type**: [e.g., library/cli/web-service/mobile-app/compiler/desktop-app or NEEDS CLARIFICATION]

**Performance Goals**: [domain-specific, e.g., 1000 req/s, 10k lines/sec, 60 fps or NEEDS CLARIFICATION]

**Constraints**: [domain-specific, e.g., <200ms p95, <100MB memory, offline-capable or NEEDS CLARIFICATION]

**Scale/Scope**: [domain-specific, e.g., 10k users, 1M LOC, 50 screens or NEEDS CLARIFICATION]

## Constitution Check

**GATE: Must pass before Phase 0 research and MUST be re-checked after
Phase 1 design.**

Evaluate this plan against the live constitution at
`.specify/memory/constitution.md`.

For each applicable principle, record:
- PASS — plan complies
- N/A — principle is genuinely not applicable, with a brief reason
- EXCEPTION REQUIRED — plan would violate or extend a principle

At minimum, explicitly consider:

1. Canonical identity / deterministic ingestion impact
2. Service and database boundary impact
3. Whether retrieval/generation architecture is being changed and what
   evaluation evidence justifies it
4. Model-routing provenance/fallback non-regression
5. Embedding-index compatibility or re-embedding implications
6. GitHub issue traceability
7. ADR/audit references without restatement or conflict
8. Test and evaluation obligations

Any EXCEPTION REQUIRED result MUST be documented in Constitution Exceptions /
Complexity Tracking and surfaced for review before implementation proceeds.

## Architecture Impact

**Services touched**:
- [service/path]

**Database ownership impact**:
- None / [describe]

**Public/API contract impact**:
- None / [describe]

**Canonical identity / graph impact**:
- None / [describe]

**Embedding/index impact**:
- None / [describe]

**Model-routing impact**:
- None / [describe]

**Relevant ADRs**:
- [ADR references only; do not restate them]

**Known conflicts**:
- None / [describe]

## Evaluation Plan

**Evaluation required**: Yes / No
**Reason**: [Principle III / VIII applicability]

**Baseline**:
- [current system/configuration being measured]

**Corpus / fixture**:
- [evaluation dataset]

**Metrics**:
- [retrieval / ranking / generation / latency metrics]

**Comparison method**:
- [how baseline and candidate behavior are compared]

**Decision gate**:
- [what evidence determines go/no-go/follow-up]

**Evidence location**:
- [file/path where results will be recorded]

## Required Non-Regressions

- [Existing behavior that must continue to work]
- [Existing tests that must remain green]
- [Operational behavior that must be preserved]

## Project Structure

### Documentation (this feature)

```text
specs/[###-feature]/
├── plan.md              # This file (/speckit-plan command output)
├── research.md          # Phase 0 output (/speckit-plan command)
├── data-model.md        # Phase 1 output (/speckit-plan command)
├── quickstart.md        # Phase 1 output (/speckit-plan command)
├── contracts/           # Phase 1 output (/speckit-plan command)
└── tasks.md             # Phase 2 output (/speckit-tasks command - NOT created by /speckit-plan)
```

### Source Code (repository root)

<!--
  Inspect the live repository and list only the existing directories/files that
  this feature will create or modify.

  Do not infer a generic single-project/web/mobile layout. Preserve
  established service boundaries from the constitution and governing ADRs
  (e.g. ingestion_service, vector_store_service, llm_service, rag_orchestrator,
  shared/ — see Constitution Principle II and CLAUDE.md's architecture map).
-->

```text
[actual repository paths affected by this feature]
```

**Structure Decision**: [Explain why these existing components are the
correct implementation locations.]

## Constitution Exceptions / Complexity Tracking

> **Fill ONLY if Constitution Check has EXCEPTION REQUIRED entries that must be justified.**
> An entry here does not automatically authorize the exception. Any
> constitutional exception must be explicitly reviewed before implementation.

| Principle / Constraint | Proposed Exception or Added Complexity | Why Necessary | Simpler Compliant Alternative Rejected Because |
|-------------------------|------------------------------------------|----------------|--------------------------------------------------|
| [e.g., Principle II] | [e.g., new service touches Postgres directly] | [current need] | [why the existing boundary is insufficient] |
