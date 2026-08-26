<!--
SYNC IMPACT REPORT
Version change: TEMPLATE → 1.0.0 (initial ratification)
Modified principles: n/a (first adoption)
Added sections: Core Principles I-VIII; Governance
Removed sections: [SECTION_2_NAME]/[SECTION_2_CONTENT] and [SECTION_3_NAME]/[SECTION_3_CONTENT]
  placeholders from the template are not used — engineering invariants live in the
  Core Principles, process/enforcement rules live in Governance; no separate
  free-form section was needed for this project.
Templates requiring follow-up: .specify/templates/plan-template.md, spec-template.md,
  tasks-template.md, checklist-template.md have not yet been reviewed for consistency
  with this constitution. Review them before running /speckit-specify for SPEC 001.
Deferred TODOs: none. Every placeholder below was resolved from the fact-checked SDD
  adoption proposal (DOCS/proposals/sdd-spec-kit-adoption.md, issue #60) and the
  existing ADRs (DOCS/adr/) — no unknowns remain.
-->

# rag-foundry-universal Constitution

## Core Principles

### I. Deterministic Ingestion & Canonical Identity Stability
Re-ingesting a repo deletes all its rows and fully reprocesses; the resulting
document IDs and relationships MUST be byte-identical across runs, or ingestion
is broken. Canonical IDs (file = `<relative_path>`; symbol =
`<relative_path>#<Class.method>`) MUST NOT fold in parameters, line numbers, AST
node IDs, hashes, timestamps, or import-resolution results. Renaming a symbol is
*expected* to change its ID — there is no lineage tracking, and none should be
retrofitted without a new ADR. No LLM calls are permitted anywhere in the
ingestion path. (Source: ADR-030, ADR-031.)

### II. Service & Database Boundaries
`ingestion_service` owns all database access exclusively; no other service may
touch Postgres directly. Services communicate only over HTTP through
`shared/config/service_urls.py` — a service URL MUST NOT be hardcoded anywhere
else. Every ingestion entrypoint MUST construct its pipeline via
`ingestion_service/src/core/pipeline_factory.py::build_pipeline()`; API modules
MUST NOT construct `IngestionPipeline`, an embedder, or a vector store directly.
(Source: ADR-038; system architecture in CLAUDE.md.)

### III. Evidence Before Retrieval/Generation Architecture Changes
No retrieval or generation component (reranker, hybrid lexical+vector search,
chunking rework, embedding-model migration) may be added because another RAG
implementation uses it. Such changes require measured evidence from the RAG
quality evaluation methodology (`DOCS/audit/08-RAG-Quality-Evaluation-Methodology.md`,
WP-Q0 / issue #49). This generalizes the project's existing rank 8-20 reranker
gate into a repo-wide rule: retrieval architecture follows evidence, not fashion.

### IV. Protect Existing Model-Routing Observability (Non-Regression)
Remote/local LLM fallback (Tailscale Ollama → local Ollama) and end-to-end
model-used provenance are ALREADY IMPLEMENTED and verified in code
(`model_registry.py`, `llm_client.py`, `rag_orchestrator`'s service layer, the
Gradio UI). This principle is a non-regression guard, not a build target: any
change touching generation or summarization routing MUST preserve response-level
visibility into which model actually served the request. Do not re-implement
this from scratch under the assumption it doesn't exist.

### V. Embedding Lifecycle Discipline
The embedding model (`mxbai-embed-large`, 1024-dim) is fixed. Changing it
invalidates every stored vector and MUST be treated as its own project, with a
dedicated re-embedding job and per-index model tagging — never a silent swap.
(Source: `DOCS/audit/06-LLM-Provider-LiteLLM-Plan.md` §5, referenced here, not
restated in full.)

### VI. Every Change Traces to a Documented Issue
No implementation work proceeds without a GitHub issue. Where the work maps to
a roadmap phase (`DOCS/audit/07-Roadmap.md`), the issue references that phase
in its title or body as plain text; this repo does not use the GitHub
Milestones feature. A spec, plan, or task list generated under this
constitution MUST cite its tracking issue number.

### VII. Specs and Plans Reference ADRs, Never Restate Them
A spec may say "must preserve canonical identity per ADR-031" but MUST NOT
restate the ADR's rule in its own words, and the same applies to
`DOCS/audit/` findings. Restating invites the spec and the ADR/audit doc to
drift into competing versions of the same rule, at which point neither is
authoritative. Any apparent conflict between a spec and an ADR MUST be
surfaced explicitly in the spec — never silently resolved by picking one
wording over the other.

### VIII. Test-Guided Development
For each issue, define acceptance criteria as observable behavior (an HTTP
response shape or DB state), and write at least a skeletal test before or
immediately alongside the first implementation spike, expanding coverage as
confidence grows. (Source: `docs-archive/Rules-to-help-me-coding.md`.)

## Governance

This constitution supersedes ad hoc process practice for any work performed
under Spec Kit (`specs/NNN-feature/` and the `/speckit-*` workflow). Where this
document would conflict with a still-valid ADR in `DOCS/adr/` on a specific
technical fact, the ADR remains authoritative for that fact (per Principle
VII) — the conflict must be surfaced and reconciled by amending one document
or the other, never silently overridden in a spec.

- **No direct commits to `main`.** All changes land via branch + pull request,
  including documentation-only changes.
- **No AI attribution in commit trailers or PR bodies.** No `Co-Authored-By`
  trailers, no "Generated with Claude Code" text — AI-assisted development is
  credited in `README.md` instead.
- **Amendments require the same verification discipline used to ratify this
  document.** A claim about "current system behavior" must be checked against
  code, config, or git history before being written into this constitution —
  not taken on faith from external discussion (e.g. a ChatGPT conversation
  without live repo access).
- **Versioning is semantic** (MAJOR.MINOR.PATCH): MAJOR for backward-incompatible
  principle removal or redefinition, MINOR for a new principle or materially
  expanded guidance, PATCH for wording or clarification only.
- Complexity or an exception to any principle above must be justified
  explicitly in the spec or plan that introduces it, not silently absorbed.

**Version**: 1.0.0 | **Ratified**: 2026-08-26 | **Last Amended**: 2026-08-26
