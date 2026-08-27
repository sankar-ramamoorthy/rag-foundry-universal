<!--
SYNC IMPACT REPORT
Version: 1.0.0 (pre-ratification correction pass — not yet ratified as of this
  revision; see Governance for the ratification date this version was approved).
Corrections made before ratification (user review, 2026-08-26):
  - Principle I rewritten: no longer states re-ingestion as always
    delete-and-fully-reprocess. ADR-030 defers incremental indexing to "a
    future milestone" it does not forbid; DOCS/audit/04-Scalability-Plan.md
    WP-S6 (incremental ingestion) explicitly requires an incremental result to
    equal a from-scratch rebuild per ADR-036. The original wording would have
    made WP-S6 a constitutional violation. Also removed "document IDs ...
    byte-identical" — verified in shared/models/document_node.py that
    `document_id` is an internal DB primary key, distinct from `canonical_id`;
    the real invariant is canonical identity + relationship topology, not the
    internal key.
  - Principle II rewritten: verified in docker-compose.yml and
    vector_store_service/src/core/db/models/vector_embedding.py that
    `vector_store_service` has its own `DATABASE_URL` and its own SQLAlchemy
    models — it does access Postgres directly, for its own tables. This
    matches DOCS/audit/00-Audit-Overview.md:84 ("All DB access stays inside
    ingestion_service (ADR-045 boundary), except vector_store_service's own
    tables"). The original "no other service may touch Postgres directly" was
    factually wrong.
  - Principle III: broadened the parenthetical to include prompt/context-
    assembly changes, since bad generation can come from context construction
    rather than the model itself.
  - Principle V: reworded "the embedding model is fixed" to "the active
    embedding index is model-bound" — the rule is that a change must be
    deliberate and project-scoped, not that no change can ever happen.
  - Principle VIII: added a sentence requiring evaluation evidence (not just
    conventional tests) for quality-sensitive retrieval/ranking/generation
    changes, cross-referencing Principle III.
Added sections: Core Principles I-VIII; Governance
Removed sections: [SECTION_2_NAME]/[SECTION_2_CONTENT] and [SECTION_3_NAME]/[SECTION_3_CONTENT]
  placeholders from the template are not used — engineering invariants live in the
  Core Principles, process/enforcement rules live in Governance; no separate
  free-form section was needed for this project.
Templates requiring follow-up: .specify/templates/plan-template.md, spec-template.md,
  tasks-template.md, checklist-template.md have not yet been reviewed for consistency
  with this constitution. Review them before running /speckit-specify for SPEC 001.
Deferred TODOs: none. Every claim below was checked against current code/config
  (docker-compose.yml, shared/models/document_node.py, vector_store_service/src/core/db/)
  and current ADRs/audit docs (DOCS/adr/, DOCS/audit/00-Audit-Overview.md), not
  taken on faith from the originating proposal.
-->

# rag-foundry-universal Constitution

## Core Principles

### I. Deterministic Ingestion & Canonical Identity Stability
Re-ingestion MUST produce a repository state equivalent to a clean rebuild for
identical inputs: canonical identities (per ADR-031) and relationship topology
(per ADR-030) must match, whether ingestion is full or incremental.
Implementations MAY use full-rebuild or incremental ingestion (see WP-S6,
`DOCS/audit/04-Scalability-Plan.md`), provided an incremental result is
verifiably equivalent to a from-scratch rebuild, preserving ADR-036 semantics.
This invariant governs canonical identity and graph topology — not
`document_id`, the internal DB primary key generated at persistence time,
which is not required to be stable across rebuilds. Renaming a symbol is
*expected* to change its canonical ID — there is no lineage tracking, and none
should be retrofitted without a new ADR. No LLM calls are permitted anywhere
in the ingestion path.

### II. Service & Database Boundaries
Database ownership follows the boundaries the governing ADRs establish (the
ADR-045 boundary, as recorded in `DOCS/audit/00-Audit-Overview.md`):
`ingestion_service` owns the graph/document metadata tables (`document_nodes`,
`document_relationships`) exclusively; `vector_store_service` may directly
access only the vector-store tables it owns (it holds its own `DATABASE_URL`
and SQLAlchemy models under `vector_store_service/src/core/db/`). No other
service may bypass those boundaries. Beyond that split, services communicate
only over HTTP through `shared/config/service_urls.py` — a service URL MUST
NOT be hardcoded anywhere else. Every ingestion entrypoint MUST construct its
pipeline via `ingestion_service/src/core/pipeline_factory.py::build_pipeline()`;
API modules MUST NOT construct `IngestionPipeline`, an embedder, or a vector
store directly. (Source: ADR-038 for pipeline construction.)

### III. Evidence Before Retrieval/Generation Architecture Changes
No retrieval or generation component (reranker, hybrid lexical+vector search,
chunking rework, embedding-model migration, prompt/context-assembly changes)
may be added because another RAG implementation uses it. Such changes require
measured evidence from the RAG quality evaluation methodology
(`DOCS/audit/08-RAG-Quality-Evaluation-Methodology.md`, WP-Q0 / issue #49).
This generalizes the project's existing rank 8-20 reranker gate into a
repo-wide rule: retrieval and generation architecture follows evidence, not
fashion.

### IV. Protect Existing Model-Routing Observability (Non-Regression)
Remote/local LLM fallback (Tailscale Ollama → local Ollama) and end-to-end
model-used provenance are ALREADY IMPLEMENTED and verified in code
(`model_registry.py`, `llm_client.py`, `rag_orchestrator`'s service layer, the
Gradio UI). This principle is a non-regression guard, not a build target: any
change touching generation or summarization routing MUST preserve response-level
visibility into which model actually served the request. Do not re-implement
this from scratch under the assumption it doesn't exist.

### V. Embedding Lifecycle Discipline
The active embedding index is model-bound (currently `mxbai-embed-large`,
1024-dim): changing the embedding model invalidates every vector built against
the prior model. Such a change is allowed, but only deliberately — as its own
project, with a dedicated re-embedding job and per-index model tagging, never
a silent swap. (Source: `DOCS/audit/06-LLM-Provider-LiteLLM-Plan.md` §5,
referenced here, not restated in full.)

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
confidence grows. Quality-sensitive changes to retrieval, ranking, or
generation additionally require evaluation evidence from the RAG quality
evaluation methodology (Principle III) — conventional tests alone are not
sufficient to justify them. (Source: `docs-archive/Rules-to-help-me-coding.md`.)

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
