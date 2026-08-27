# Implementation Plan: RAG Quality Baseline (WP-Q0)

**Branch**: `001-rag-quality-baseline` | **Date**: 2026-08-26 | **Spec**: [spec.md](./spec.md)

**Tracking Issue**: #49

**Roadmap Context**: Phase 2.75 (WP-Q0)

**Input**: Feature specification from `/specs/001-rag-quality-baseline/spec.md`

**Note**: This template is filled in by the `/speckit-plan` command; its definition describes the execution workflow.

## Summary

Run the WP-Q0 evaluation methodology (`DOCS/audit/08-RAG-Quality-Evaluation-Methodology.md`)
end to end against a small curated corpus, using only the existing, unmodified
system: ingest the corpus, run known-answer queries through the existing
retrieval path, record the six-field diagnostic surface per question, run the
clean-context generation test on failures only, classify every failure, and
produce an explicit go/no-go verdict on reranking. There is no new component
to design — this plan's "technical approach" is a measurement procedure
against production code that already exists, not a system to build.

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

**Language/Version**: N/A — no new service code is written. Existing services
(Python 3.12, `uv`-managed) are exercised as an external client, not modified.

**Primary Dependencies**: N/A — no dependency is added to any service's
`pyproject.toml`.

**Storage**: N/A — no new table, column, or migration. Evaluation reads
existing data through existing HTTP endpoints; results are recorded as
markdown files under `DOCS/test_results/`, not in Postgres.

**Testing**: N/A in the pytest sense — no new unit/integration test suite is
required for the endpoints being called (they already have their own tests,
which this plan must not break — see Required Non-Regressions). This
feature's own acceptance mechanism *is* the evaluation evidence produced
(Constitution Principle VIII).

**Target Platform**: The existing dockerized stack (`docker compose up`),
run locally. No new deployment target.

**Project Type**: N/A — this is a measurement exercise against an existing
system, not a software component being built.

**Performance Goals**: N/A — this plan measures current retrieval/generation
performance and quality; it does not set a new performance target. What gets
measured is listed under Evaluation Plan below.

**Constraints**: N/A — no new operational constraint is introduced.

**Scale/Scope**: A small, fixed-size evaluation corpus — one ingested repo
(`shared/smoke_repo`) plus 2-3 documents — and 8-12 known-answer questions
(spec.md FR-001/FR-002). This is intentionally small; WP-Q0 is a diagnostic
pass, not a load test.

## Constitution Check

**GATE: Must pass before Phase 0 research and MUST be re-checked after
Phase 1 design.**

Evaluate this plan against the live constitution at
`.specify/memory/constitution.md`.

| # | Principle | Status | Justification |
|---|---|---|---|
| I | Deterministic Ingestion & Canonical Identity Stability | N/A | No ingestion behavior is changed. The corpus is ingested through the existing, unmodified pipeline. If evaluation surfaces an ingestion-determinism defect, it is filed as a separate issue (spec.md Non-Goals / FR-008), not fixed under this plan. |
| II | Service & Database Boundaries | PASS | No new service, table, or boundary crossing. This plan only calls existing HTTP endpoints (`ingestion_service`, `vector_store_service`, `rag_orchestrator`) as an external client. |
| III | Evidence Before Retrieval/Generation Architecture Changes | PASS | This plan *is* the evidence-gathering step Principle III requires before any reranker/hybrid/chunking/embedding change — see Evaluation Plan. |
| IV | Protect Existing Model-Routing Observability (Non-Regression) | PASS | No routing change. The clean-context test reads the existing model-used provenance; it does not modify routing logic. |
| V | Embedding Lifecycle Discipline | PASS | No embedding model change and no re-embedding. The existing `mxbai-embed-large` index is queried as-is. |
| VI | Every Change Traces to a Documented Issue | PASS | Issue #49, Phase 2.75 (`DOCS/audit/07-Roadmap.md`). |
| VII | Specs and Plans Reference ADRs, Never Restate Them | PASS | This plan cites ADR-030/039/040/045 and the methodology doc by reference (see Architecture Impact, Evaluation Plan) without restating their rules. |
| VIII | Test-Guided Development | PASS | The evaluation evidence this plan produces *is* the acceptance mechanism for issue #49 (Principle VIII's evaluation-evidence clause). Required Non-Regressions covers what conventional tests must still guard. |

**Result: no EXCEPTION REQUIRED entries.** Constitution Exceptions /
Complexity Tracking below is intentionally empty.

## Architecture Impact

**No production architecture change. Evaluation harness/artifacts only.**

**Services touched**:
- None (read-only HTTP client calls to `ingestion_service`,
  `vector_store_service`, `rag_orchestrator`, and `llm_service`'s existing
  `POST /generate` endpoint for the clean-context step — using the same
  generation path production uses, with only the context substituted, per
  research.md Decision 4; no service code is modified)

**Database ownership impact**:
- None

**Public/API contract impact**:
- None — no endpoint is added, removed, or changed

**Canonical identity / graph impact**:
- None — the corpus is ingested through the existing pipeline; canonical IDs
  are whatever that pipeline already produces

**Embedding/index impact**:
- None — no embedding model change, no re-embedding

**Model-routing impact**:
- None — existing remote→local Ollama fallback is exercised as-is during the
  clean-context test (per spec.md's Assumptions), not modified

**Relevant ADRs**:
- ADR-030 (repository isolation — cross-repo leakage found during evaluation
  would be a correctness bug against this, filed separately per spec.md
  Non-Goals)
- ADR-039 / ADR-040 (artifact-level embedding — why code has no
  chunk-boundary question in this evaluation)
- ADR-045 (the hybrid vector-graph retrieval flow being measured)

**Known conflicts**:
- None

## Evaluation Plan

**Evaluation required**: Yes
**Reason**: Constitution Principle III (evidence required before any
retrieval/generation architecture change) and Principle VIII (evaluation
evidence required for quality-sensitive work) both apply directly — this
plan's entire purpose is satisfying them for the reranker decision.

**Baseline**:
- The current, unmodified production retrieval and generation pipeline
  (`rag_orchestrator`'s `/v1/rag` and `/v1/rag/simple` paths, current
  chunking, current embedding model, current prompting). There is no
  candidate/changed system in this plan — the baseline itself is the subject
  being measured (see spec.md's Evaluation Evidence section).

**Corpus / fixture**:
- `shared/smoke_repo`, ingested via the existing `/v1/ingest-repo` endpoint
- 2-3 representative documents, ingested via the existing `/v1/ingest/file`
  endpoint (exact document selection is a Phase 0 decision — see research.md)

**Metrics**:
- Recall@5 and Recall@20 across the known-answer question set
- Cross-repo leakage rate (expected zero; nonzero is a correctness bug, not a
  tuning signal)
- Duplicate/near-duplicate rate within the top-20 candidate set
- Clean-context grounding, citation, and omission scores per failed question
- Clean-context generation latency (cold and warm)
- Failure-class distribution (ingestion / chunking-or-retrieval / rank 8-20 /
  generation-or-prompting)

**Comparison method**:
- No A/B comparison — there is no candidate system. Each question's recorded
  diagnostic row is compared against the decision table in
  `DOCS/audit/08-RAG-Quality-Evaluation-Methodology.md` §2/§4 to classify its
  failure mode, if any.

**Decision gate**:
- Reranking is justified only if a non-trivial fraction of failures
  consistently land at rank 8-20 and aren't already explained by a chunking
  or generation defect (methodology §4). If "absent from top 20" dominates,
  the next work is chunking/embedding/filtering. If "top-3-but-poor-answer"
  dominates, the next work is prompting/model choice. If neither dominates,
  the negative result is recorded explicitly.

**Evidence location**:
- A single file under `DOCS/test_results/` (exact filename decided in
  research.md) containing the diagnostic table, clean-context scores, failure
  classifications, and final verdict together.

## Required Non-Regressions

- `/v1/rag`, `/v1/rag/simple`, `/v1/ingest-repo`, and `/v1/ingest/file`
  continue to behave exactly as they do today — this plan only calls them as
  a read/query client; it does not modify their code.
- Existing test suites for `ingestion_service`, `vector_store_service`,
  `rag_orchestrator`, and `llm_service` remain green — nothing in this plan
  touches their source.
- Existing remote→local Ollama fallback behavior is exercised, not altered,
  by the clean-context generation step.
- Ingesting the evaluation corpus is a normal write through the existing
  ingestion path (the same as ingesting any other repo/document) — it is not
  a schema change or a new write path.

## Project Structure

### Documentation (this feature)

```text
specs/001-rag-quality-baseline/
├── plan.md              # This file
├── research.md          # Phase 0 output
├── data-model.md         # Phase 1 output
├── quickstart.md         # Phase 1 output
└── tasks.md              # Phase 2 output (/speckit-tasks — not created here)
```

`contracts/` is intentionally omitted: this feature exposes no new interface
to users or other systems (it is a read-only client of existing endpoints),
so there is nothing to contract-document per the plan template's own
skip-if-purely-internal guidance.

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
DOCS/test_results/       # new: this feature's evidence artifact (diagnostic
                          # table, clean-context scores, failure classification,
                          # final verdict) — the only durable output
specs/001-rag-quality-baseline/   # this spec/plan/tasks tree
specs/001-rag-quality-baseline/scripts/   # optional: scratch aggregation script (see below)
```

No file under `ingestion_service/`, `vector_store_service/`, `rag_orchestrator/`,
`llm_service/`, `shared/`, or `gradio/` is created or modified by this plan.

**Scratch-script allowance**: Scratch scripts MAY be used for deterministic
aggregation or arithmetic over already-recorded evaluation evidence (e.g.
tallying Recall@5/20 percentages or duplicate counts from the Diagnostic
Record rows). They MUST NOT become production dependencies, alter the RAG
pipeline, or expand this spec into a reusable evaluation subsystem — no new
service, framework, database, API, or abstraction layer. Manual arithmetic
over recorded evidence carries real transcription/math-error risk, so
automating the aggregation step itself is preferred over doing it by hand;
what's excluded is building eval *infrastructure*, not automating arithmetic.
If a script is used and materially improves reproducibility, commit it under
`specs/001-rag-quality-baseline/scripts/` (colocated with this spec's
artifacts, not any service's package) rather than leaving it disposable and
unversioned; if it's trivial (a handful of lines) and genuinely one-shot,
leaving it uncommitted is also acceptable.

**Structure Decision**: Because spec.md's Non-Goals excludes any
implementation change, the only durable repository artifact this feature
produces is the evidence record under `DOCS/test_results/` (per the
roadmap's "nothing ships without its benchmark/eval delta recorded" rule)
plus the SDD spec/plan/tasks tree itself. This is the correct location
because it matches the existing convention already used by other WPs
(`DOCS/test_results/`) rather than inventing a new evaluation-artifacts
location.

## Constitution Exceptions / Complexity Tracking

> **Fill ONLY if Constitution Check has EXCEPTION REQUIRED entries that must be justified.**
> An entry here does not automatically authorize the exception. Any
> constitutional exception must be explicitly reviewed before implementation.

None. The Constitution Check above produced no EXCEPTION REQUIRED entries —
this table is intentionally left empty rather than filled with placeholder
rows.

---

## Post-Phase-1 Constitution Re-Check

Re-evaluated after Phase 1 design (`data-model.md`, `quickstart.md` below):
no new entity, endpoint, or service boundary was introduced by the design
artifacts — `data-model.md` describes the fields of the markdown evidence
tables under `DOCS/test_results/`, not a database schema. The Constitution
Check table above is unchanged; no EXCEPTION REQUIRED entries were
introduced during design.
