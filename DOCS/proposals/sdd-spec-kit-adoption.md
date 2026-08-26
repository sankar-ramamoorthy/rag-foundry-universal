---
title: "Proposal — Adopting Spec-Driven Development (GitHub Spec Kit)"
date: 2026-08-25
type: proposal
status: accepted-conceptually (execution scoped to init + constitution only)
horizon: n/a
tags:
  - proposal
  - sdd
  - spec-kit
  - process
related:
  - "[[07-Roadmap]]"
  - "[[08-RAG-Quality-Evaluation-Methodology]]"
  - "[[06-LLM-Provider-LiteLLM-Plan]]"
---

# 🧭 Proposal — Adopting Spec-Driven Development (GitHub Spec Kit)

> [!warning] This is a suggestion, not a decision
> This document is a **written-down brainstorm**, produced from an external ChatGPT
> conversation about introducing [github/spec-kit](https://github.com/github/spec-kit)
> (the `specify` CLI: `/specify` → `/plan` → `/tasks` slash commands, a project
> "constitution," and `specs/NNN-feature/` folders) into this repo's workflow.
> Nothing here has been adopted. No `.specify/` directory or `specs/` folder exists
> in the repo as of this writing — confirmed by search, not assumed. Treat every
> claim below as a candidate for review, not as an instruction to future agents.

## 0 · Why this exists

The user has been discussing SDD adoption with ChatGPT, which does not have live
access to this codebase and was reasoning from partial/stale context. Before acting
on any of it, the specific factual claims about *current system behavior* were
checked against the actual repo (config files, code, git history) rather than taken
on faith. This doc records what checked out, what needed correction, and the
proposed adoption sequence — so a future session (or the user, tomorrow) can pick
this up without re-deriving it.

## 1 · Fact-check of the ChatGPT claims

### 1.1 Inference topology — verified accurate

Checked against `.env`, `llm_service/models.yaml`, and `shared/embedders/`:

```text
Generation (default route):
  remote Ollama over Tailscale (100.105.24.12), Qwen3:4b
  → automatic fallback to local Ollama (host.docker.internal), phi4-mini:latest

Summarization (/v1/summarize):
  same remote Ollama box, granite4:350m
  → automatic fallback to local

Embeddings:
  local Ollama ONLY (mxbai-embed-large:latest, 1024-dim)
  no remote/LiteLLM path exists — shared/embedders/factory.py only wires up
  OllamaEmbedder (local OLLAMA_BASE_URL) and a MockEmbedder for tests
```

This is driven by `LLM_DEFAULT_ALIAS=remote` in the gitignored `.env`, which is
machine-specific by design (see `llm_service/models.yaml` header comment) — a
fresh clone without that env var defaults to local-only, no remote dependency.

### 1.2 "Embeddings changes require re-embedding" — verified, and it's already written down

`DOCS/audit/06-LLM-Provider-LiteLLM-Plan.md` §5 already states this as an explicit
non-goal, near-verbatim to what ChatGPT said:

> Embeddings via LiteLLM — possible, but embedding-model change invalidates every
> stored vector (dimension + space). Keep `mxbai-embed-large` fixed; treat
> embedding-model migration as its own project with a re-embedding job and
> per-index model tagging.

So this isn't a new insight to add — it's an existing decision. The proposal below
just says: carry it forward as an invariant in whatever SDD constitution gets
written, rather than re-deriving it.

### 1.3 "Fallback must be observable / response records model actually used" — already implemented, not just proposed

ChatGPT listed this as an invariant to *add*. It already exists: `llm_service`'s
model registry/client, `rag_orchestrator`'s service layer, and the Gradio UI all
carry a model-used field end to end (verified in code — `model_registry.py`,
`llm_client.py`, `rag_orchestrator/src/core/service.py`, `rag_orchestrator/src/api/v1/models.py`,
`ingestion_service/src/ui/gradio_app.py` — and confirmed live via screenshot per
the [[07-Roadmap|Phase 2.5]] exit checklist). Correction: this is a **thing to
protect going forward**, not a gap to fill.

### 1.4 Roadmap position — verified accurate

Phase 1, Phase 2, and Phase 2.5 are complete; Phase 2.75 (`WP-Q0` / issue #49, the
RAG quality baseline eval) is the next unstarted work, gating Phase 3/4. This
matches both `DOCS/audit/07-Roadmap.md` and the actual git history (latest merged
PR is #59, deferring issue #41 to Phase 5) — the roadmap doc is current, not stale.

### 1.5 Diagnostic order / reranker gate — verified accurate, and already the project's stated methodology

`DOCS/audit/08-RAG-Quality-Evaluation-Methodology.md` already specifies the
ingestion → chunking → retrieval recall → generation → reranking-only-if-proven
order and the rank-8–20 reranker decision gate. This is existing project
methodology, not something SDD would introduce — the proposal is to make it the
first formal *spec* under whatever SDD tooling gets adopted, not to invent it.

## 2 · What's actually new in the ChatGPT proposal

Stripping out the parts that already exist in the repo, the genuinely new
suggestions are:

1. **Install `github/spec-kit`** (the `specify` CLI) — not currently installed;
   confirmed no `.specify/`, `specs/`, or spec-kit slash commands anywhere in this
   repo.
2. **Write a project "constitution"** distilled from the existing ADRs
   (`DOCS/adr/`) and `docs-archive/Rules-to-help-me-coding.md`, rather than
   starting from a blank template.
3. **Convert `WP-Q0` (issue #49) into the first formal Spec Kit spec**, instead of
   just running it as an ad hoc work package like prior WPs.
4. **Sequence hybrid retrieval / reranking / chunking / embedding decisions as
   *outputs* of that eval**, not pre-committed features — i.e., treat the Phase
   2.75 gate as binding on whatever SDD specs get written next, not something SDD
   adoption should bypass.
5. **A candidate constitution principle:** "Retrieval architecture changes require
   measured evidence from the quality evaluation; no component is added solely
   because another RAG implementation uses it." This is a generalization of the
   existing reranker gate (§4 of the evaluation methodology doc) into a
   repo-wide rule.
6. **A second constitution principle, added on review (2026-08-26):** SDD specs
   must not become a second source of truth for facts already governed by
   `DOCS/adr/`. A spec may *reference* an ADR ("must preserve canonical identity
   per ADR-031") but must not restate the rule in its own words — restating
   invites the spec and the ADR to drift apart, at which point neither is
   authoritative. Same logic applies to `DOCS/audit/` findings: specs cite them,
   they don't duplicate them.

## 3 · Proposed sequence (suggestion only)

```text
Existing stable system
        │
        ▼
Install / initialize Spec Kit
        │
        ▼
Project constitution
        │
        ├── deterministic ingestion
        ├── canonical identity stability
        ├── service/DB boundaries
        ├── evidence before RAG tuning
        ├── existing remote/local model routing protected
        └── spec/ADR conflicts must be surfaced
        │
        ▼
SPEC 001
RAG Quality Baseline
        │
        ▼
Plan
        │
        ▼
Tasks
        │
        ▼
Run WP-Q0 evaluation
        │
        ▼
Evidence tells us next feature
```

**Execution stops after the constitution is drafted and reviewed** — this session
does not proceed to generating SPEC 001 / Plan / Tasks without an explicit
go-ahead. WP-Q0 becomes the first controlled SDD experiment, not something run
through automatically once the tooling exists.

## 4 · Decisions (resolved 2026-08-26)

The three open questions above are resolved as follows:

- [x] **Use the actual `specify` CLI, not discipline-only.** Borrowing only the
      ideas risks sliding back into ad-hoc issue-driven development once nobody
      remembers to follow the discipline by hand. Adopt conservatively: run
      `specify init`, inspect exactly what it creates, and don't let it rewrite
      existing project structure or historical docs.
- [x] **Folder layout — new specs live alongside, not inside, `DOCS/`:**

  ```text
  specs/
    001-rag-quality-baseline/
    002-...

  DOCS/
    adr/         # durable architectural decisions
    audit/       # findings, roadmap, historical plans
    proposals/   # ideas awaiting adoption (this file's home)
  ```

  `DOCS/adr/` and `DOCS/audit/` are not moved or rewritten. Specs reference them
  (see the drift-avoidance principle in §2.6) rather than restating them.
- [x] **First spec is Phase 2.75 / WP-Q0 (RAG Quality Baseline), not hybrid
      search.** This session drafts SPEC 001 together with the user once the
      constitution is in place; Claude/Codex then turns it into a plan and
      tasks. Hybrid retrieval, reranking, chunking rework, etc. are downstream
      *outputs* of the WP-Q0 evaluation, not pre-committed next specs.

> [!note] Status
> Conceptually approved (2026-08-26): install Spec Kit, draft the constitution,
> stop before generating SPEC 001/Plan/Tasks pending explicit go-ahead. Tracked
> as issue [#60](https://github.com/sankar-ramamoorthy/rag-foundry-universal/issues/60).
> WP-Q0/issue #49 itself has not been started — SPEC 001 for it is follow-up
> work after the constitution lands, not part of issue #60's scope.
