---
title: "Audit Overview — rag-foundry-universal"
date: 2026-07-09
type: audit-index
status: complete
auditor: claude-fable-5
tags:
  - audit
  - moc
  - rag-foundry
aliases:
  - Audit MOC
  - Audit Index
---

# 🔍 Audit Overview — rag-foundry-universal

> [!abstract] Purpose
> Full technical audit of the `rag-foundry-universal` codebase, conducted 2026-07-09 against the current working tree. Every finding cites `file:line`. Companion documents contain **codex/Claude-ready work packages** with acceptance criteria — no code was changed during this audit.

## 📚 Audit Documents (Map of Content)

| Doc | Question it answers | Verdict in one line |
|---|---|---|
| [[01-Codebase-Audit-Findings]] | What is broken or fragile *today*? | ~20 concrete defects, 5 of them silently corrupt the graph |
| [[02-Graph-Depth-Analysis]] | **Is the graph too shallow?** | **Yes** — 6 node types, 3 working edge types, and call resolution is mostly broken |
| [[03-Multi-Language-Graph-Plan]] | How to support Rust / TypeScript / Java / JavaScript? | Tree-sitter + language-agnostic IR; the canonical-ID model survives intact |
| [[04-Scalability-Plan]] | How to handle massive codebases? | Fix O(N²) ingestion first, then ANN indexes, job queue, incremental ingestion |
| [[05-Enterprise-Platform-Plan]] | Laptop → enterprise web product? | Auth, multi-tenancy, real frontend, K8s, observability — phased plan |
| [[06-LLM-Provider-LiteLLM-Plan]] | LiteLLM + model switching? | Replace `llm_service` internals with LiteLLM Router; 2–3 day work package |
| [[07-Roadmap]] | In what order? | 5 phases, each decomposed into agent-sized work packages |
| [[08-RAG-Quality-Evaluation-Methodology]] | Is a reranker actually needed? | Not yet — verify chunking, retrieval recall, and clean-context generation first |

## 📍 Current status (2026-07-20 — supersedes the maturity claim below)

> [!tip] Phases 1–2 are implementation-complete and operationally hardened. RAG retrieval and answer quality have not yet been formally validated.

- **Phase 1 (foundation) and Phase 2 (graph depth + LLM freedom) are done** — see [[07-Roadmap]], now checked off against actual merged PRs rather than aspirational checkboxes. O(N) graph build, batch/atomic persistence, HNSW indexing, full call/inheritance resolution, LiteLLM routing with a live remote-Ollama endpoint and fallback chain.
- **Beyond the original plan**, reactive hardening from live Docker testing caught and fixed real defects: repo_id being dropped in the query path, source labels resolving to UUIDs instead of names, a fallback-chain timeout regression, and (ongoing) two-repo isolation / model-alias switching checks. This is evidence the infrastructure works, not evidence the RAG answers are good.
- **What is not yet proven:** whether retrieval consistently surfaces the correct evidence, and whether generation produces grounded, complete answers from it. [[08-RAG-Quality-Evaluation-Methodology]] is the gate for this — Phase 4's reranker (`WP-S8` in [[04-Scalability-Plan]]) stays unstarted until that evaluation says it's the actual bottleneck.
- **Phase 3 (multi-language) and the rest of Phase 4/5 are not started.**
- A precise one-line status: *the platform works; whether it works well is not yet validated.*

## 🎯 Executive Summary (as audited 2026-07-09 — historical; see status above for what has since shipped)

The project has a **sound architectural thesis** — read-only, graph-aware code intelligence with deterministic canonical identity ([[../adr/ADR-031-canonical-identity-model|ADR-031]]) — and a clean service decomposition. The thesis is worth scaling. The implementation, however, is at **prototype maturity**:

1. **The graph is real but shallow and partially broken.** Async functions are invisible, `IMPORT` edges are never created (yet the orchestrator offers an import-traversal strategy that therefore always returns nothing), method-call resolution fails for `self.x()` / `obj.x()` patterns, and call-site identity collides. See [[02-Graph-Depth-Analysis]].
2. **Ingestion is algorithmically O(N²)–O(N³)** and does one HTTP round-trip + one DB query *per artifact*. A 5k-file repo will take hours or fail. See [[04-Scalability-Plan]].
3. **Vector search has no ANN index** — every query is a sequential scan over `vector_chunks`.
4. **Zero enterprise readiness**: no auth on any endpoint, plaintext DB credentials in `docker-compose.yml`, fire-and-forget `threading.Thread` ingestion that dies with the process, no observability beyond `logging`, and a CI workflow that cannot run (file is misnamed `.github/workflows/ci/yml`). See [[05-Enterprise-Platform-Plan]].
5. **LLM layer is a hard-coded Ollama call** (`llm_service/src/core/llm_client.py:22` raises on any other provider). LiteLLM is the right fix and is cheap to adopt. See [[06-LLM-Provider-LiteLLM-Plan]].

> [!tip] The single most important strategic decision
> Introduce a **language-agnostic intermediate representation (IR)** for extraction (see [[03-Multi-Language-Graph-Plan]]) *before* deepening the Python graph. Deepen the graph **through** the IR, not through more Python-only code. Otherwise every Python-specific improvement becomes rework when Rust/TS/Java land.

## 🧭 Priority Matrix (as audited 2026-07-09 — historical; current priority is the RAG-quality baseline below)

| Priority | Theme | Why now | Status (2026-07-20) |
|---|---|---|---|
| 🔴 P0 | Correctness bugs in graph build ([[01-Codebase-Audit-Findings#P0 — Graph correctness]]) | Everything downstream reasons over wrong data | ✅ Done (Phase 1/2) |
| 🔴 P0 | O(N²) ingestion hot loops | Blocks any repo beyond toy size | ✅ Done (WP-S1) |
| 🟠 P1 | ANN index + batch embedding | Query latency and ingest throughput | ✅ Done (WP-S2/S4/S4B) |
| 🟠 P1 | LiteLLM provider abstraction | Unblocks enterprise LLM requirements; small effort | ✅ Done + extended (PR #47); Groq/NIM tracked as issue #46 |
| 🟡 P2 | Tree-sitter IR + multi-language | The headline feature ask | Not started (Phase 3) |
| 🟡 P2 | Job queue + incremental ingestion | Massive-repo readiness | Not started (Phase 4) |
| 🟢 P3 | Auth / multi-tenancy / web frontend | Enterprise productization | Not started (Phase 5) |

**Current top priority (2026-07-20):** finish the outstanding live-smoke-test acceptance checks, then execute [[08-RAG-Quality-Evaluation-Methodology]] end to end — this now gates whether any further quality work (reranker, embedding swap, chunking rework) is justified, and gates whether Phase 3/4 work proceeds on top of a system with proven answer quality.

## 📐 How the work packages are written

Every plan document decomposes into work packages shaped for handoff to **Codex (GPT-5.5)** or **Claude Sonnet 5**:

- **`WP-xx` identifier** — stable reference for tickets
- **Goal** — one sentence, observable behavior
- **Files** — exact paths to create/modify
- **Directions** — implementation guidance, constraints, and ADR references
- **Acceptance criteria** — checkbox list per the project's Test-Guided Development rules (`docs-archive/Rules-to-help-me-coding.md`)

> [!warning] Ground rules the implementing agent must respect
> - Ingestion stays deterministic — **no LLM calls in the ingestion path** (ADR-030).
> - Identity stays `(repo_id, canonical_id)`; never leak line numbers/hashes into IDs (ADR-031).
> - All DB access stays inside `ingestion_service` (ADR-045 boundary), except `vector_store_service`'s own tables.
> - Rebuilds must remain byte-identical for identical inputs (ADR-036).
