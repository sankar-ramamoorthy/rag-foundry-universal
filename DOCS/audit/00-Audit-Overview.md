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

## 📍 Current status (2026-08-29 — supersedes the 2026-08-27 status below)

> [!tip] Both WP-Q0 follow-on findings are fixed. The reranker NO-GO verdict and the "next lever is prompting/context assembly" conclusion below still stand.

- **[Issue #64](https://github.com/sankar-ramamoorthy/rag-foundry-universal/issues/64) fixed** ([#72](https://github.com/sankar-ramamoorthy/rag-foundry-universal/pull/72), merged): `hybrid_retrieve()`'s seed filter matched `doc_type="code"`, a value ingestion never wrote (codebase ingestion writes `doc_type="python source"`), so every code-repo query silently fell back to an unfiltered repo-scoped search. Fixed by filtering on `source_type` instead — the language-neutral marker `simple_service.py`'s document-RAG path already used correctly — promoted to a typed/indexed `vector_chunks` column (extending WP-S4B). Verified live: the fallback no longer fires.
- **[Issue #65](https://github.com/sankar-ramamoorthy/rag-foundry-universal/issues/65) fixed** ([#73](https://github.com/sankar-ramamoorthy/rag-foundry-universal/pull/73), merged): a module/root artifact with exactly one child covering ~the same text (a README's sole H1 section, a single-class file with no imports) produced near-duplicate seed candidates. Fixed with a retrieval-time dedup pass in `hybrid_retrieve()` — deliberately not an ingestion-time change, since ADR-039 §4 / ADR-040 §6.2 require embedding every MODULE artifact and changing that would need amending an accepted ADR plus re-ingesting every existing repo. [[09-Retrieval-Technique-Decision-Gates]]'s "Context deduplication" row is updated accordingly.
- **What is still open, per the 2026-08-27 status below:** context assembly/prompting when multiple retrieved chunks share surface phrasing but describe different referents. Not yet filed as its own issue.

## 📍 Current status (2026-08-27 — supersedes the 2026-07-20 status below)

> [!tip] Phases 1, 2, 2.5, and 2.75 are complete. RAG retrieval and answer quality have now been **empirically measured**, not just operationally hardened — and the reranker question has an evidence-based answer: **NO-GO, for now.**

- **Phase 2.75 (RAG quality baseline, issue #49, `WP-Q0`) is done.** Full evidence: `DOCS/test_results/2026-08-27-wp-q0-rag-quality-baseline.md`; summarized in [[07-Roadmap#Phase 2.75 — RAG quality baseline (empirical, precedes any Phase 4 reranker work)|the roadmap]]. 10 known-answer questions (5 code, 5 document) ran end-to-end against production `/v1/rag` and `/v1/rag/simple`: **9/10 pass.** Recall@5 was 70% via raw vector search alone vs. **90% via the production path** — graph expansion recovering 2 of the 3 raw-vector misses is the graph-aware architecture's value proposition measured directly, not just architecturally implied.
- **Reranker verdict: NO-GO.** [[04-Scalability-Plan#WP-S8 — Retrieval quality/perf at scale|WP-S8]]'s reranker sub-task stays deferred per [[08-RAG-Quality-Evaluation-Methodology#4 · Reranker decision gate|the decision gate]] — zero of the corpus's failures classified `rank-8-to-20` (the only pattern a reranker could fix). The single failure (`top-3-but-poor-answer`) was independently confirmed via a clean-context test to be a prompting/context-assembly problem, not a retrieval-rank or generation-capability problem. **Next lever: prompting/context assembly**, not a reranker.
- **Two related findings surfaced and filed, deliberately not fixed** (out of scope for an evaluation-only work package): [issue #64](https://github.com/sankar-ramamoorthy/rag-foundry-universal/issues/64) (the code-query seed filter's `doc_type` match never fires; every code query silently falls back to repo-scoped search, measurably costing rank positions) and [issue #65](https://github.com/sankar-ramamoorthy/rag-foundry-universal/issues/65) (near-duplicate chunk crowding from module/sole-child artifact embedding — a retrieval-quality/indexing finding, not a correctness bug).
- **What is newly proven, that the 2026-07-20 status below could not yet claim:** retrieval surfaces the correct evidence in the large majority of cases, and generation grounds correctly when given clean context. **What is still open:** context assembly/prompting when multiple retrieved chunks share surface phrasing (e.g. "p95 latency") but describe different referents — that failure mode, not reranking, is the next quality lever.
- **Phase 3 (multi-language) and the rest of Phase 4/5 have not started.** Per the roadmap's 2026-08-27 note, this work may now resume — with `WP-S8`'s reranker sub-task specifically excluded pending a future re-evaluation that finds rank-8–20 failures.

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
