---
title: "rag-foundry-universal — Vision & Context"
date: 2026-03-21
type: vision
status: historical
tags: [vision, historical, rag-foundry]
related:
  - "[[../README|README]]"
  - "[[audit/00-Audit-Overview]]"
---

# rag-foundry-universal — Vision & Context

> **A note to the reader:** This document was written by Claude (Anthropic's AI assistant) at the request of the repository author. It is based on a close reading of the repository README, architecture documentation, and an extended conversation with the author about design intent, architectural decisions, and the broader landscape of AI coding tools. It is an honest external assessment, not marketing copy.

> [!warning] Historical / vision document — not a current-state reference (annotated 2026-08-27)
> Written March 2026, before Phase 1/2/2.5/2.75 shipped. Read it for **design intent and rationale**, not for what the system does today — start at `README.md` and `DOCS/audit/00-Audit-Overview.md` for current state. Specifically:
> - **Envisioned here, still not built as of 2026-08-27:** nightly scheduled ingestion, snapshot/version diffing across ingestion runs ("what changed since last week"), GitHub App/PR webhook integration, and proactive diff comments. Every claim below under "The intended use case" and "workflow it is designed to support" describes this envisioned future, not shipped behavior — none of it exists in code yet.
> - **Shipped since this was written, contradicting specific claims below:** the "Where this fits" / "Current limitations" sections call cloud-LLM switching and a richer call graph forward-looking gaps. LiteLLM multi-provider routing (local Ollama, a Tailscale-reachable remote Ollama box, and Anthropic/OpenAI cloud aliases) shipped in PR #47; the call graph now includes `INHERITS`/`OVERRIDES` edges beyond the `CALL`/`DEFINES`/`IMPORT` set described here. See README.md for current specifics.
> - **Reranker framing is now stale in a specific way:** the tables below list reranker integration as simply "not implemented yet," reading as an ordinary backlog gap. As of the WP-Q0 empirical evaluation (issue #49, 2026-08-27, `DOCS/test_results/2026-08-27-wp-q0-rag-quality-baseline.md`), it is a **deliberate NO-GO pending evidence** — see `DOCS/audit/04-Scalability-Plan.md` WP-S8 — not a task waiting to be scheduled.
> - **Still accurate:** the architecture diagram, the ingestion capability matrix, the read-only design thesis, and the AI-coding-tools comparison table remain a fair description of what's built.

---

## What this project is

`rag-foundry-universal` is a **code intelligence system** — a read-only, graph-aware retrieval engine for Python codebases and their documentation. It ingests a Git repository, parses every `.py` and Markdown file, builds a persistent structural graph of the codebase, and exposes that graph for natural-language querying via LLM.

The key word is *read-only*. This system does not write, edit, or modify code. That constraint is intentional and is the source of much of its value.

---

## The problem it solves

Most AI coding tools — Aider, Claude Code, OpenCode — are built around a single loop: understand the code, then change it. Understanding and mutation are entangled in the same process. This works well for greenfield development but creates real problems in production maintenance contexts, where:

- The codebase is large, established, and has structural dependencies that aren't obvious from any single file
- Changes carry risk — a function edit can have callers in five other modules
- The team's workflow centers on pull requests, code review, and deliberate change management
- You want AI assistance that *informs* decisions, not one that autonomously makes them

This project takes a different approach: **separate understanding from mutation entirely**. The RAG system owns understanding. A coding agent (separate, human-directed) owns mutation. They compose cleanly.

---

## How it works

### Ingestion pipeline

When pointed at a Git repository, the system:

1. Parses every Python file using AST extraction, pulling out modules, classes, functions, call relationships, and import dependencies
2. Parses every Markdown file using `markdown-it-py`, extracting heading hierarchies as structured graph nodes
3. Assigns each artifact a canonical identity — `(repo_id, canonical_id)` — that is stable across ingestion runs
4. Stores everything in PostgreSQL with `pgvector`, creating both a **structural graph** (nodes and edges representing code relationships) and **vector embeddings** (for semantic similarity search)

This is meaningfully different from what Aider's repo map does. Aider extracts function signatures and shoves them into a prompt window, freshly on each request, using a token-budget ranking algorithm. `rag-foundry-universal` builds a *persistent, queryable graph* that survives across sessions and can be queried with structural precision — not just semantic similarity.

### Query paths

The system exposes two distinct query paths:

**Graph-aware code queries** — for structural questions about the codebase. These use BFS (breadth-first search) multi-hop traversal to answer questions like "what calls this function", "what does this module depend on", or "what changed in this module's relationships since the last ingestion". The answer comes from graph traversal, not from asking an LLM to guess.

**Document graph retrieval** — for questions about the codebase's documentation. Markdown files are ingested with their section hierarchy preserved as graph nodes, so questions can be answered with section-level precision rather than returning entire files.

### Architecture

The system is decomposed into clean, independently deployable services:

```
Gradio UI  →  rag_orchestrator  →  ingestion_service  →  PostgreSQL + pgvector
                                →  vector_store_service
                                →  llm_service
```

The `ingestion_service` owns all database access exclusively (per ADR-045). The orchestrator coordinates retrieval and LLM generation. The services communicate over HTTP. Everything is Docker-composed and can run locally or be deployed independently.

---

## Where this fits in the AI coding tools landscape

It helps to place this project against the tools developers are already familiar with:

| Tool | Primary use case | How it understands code | Modifies code? |
|---|---|---|---|
| **Aider** | Pair programming — targeted file edits | tree-sitter signature extraction, token-budget ranked | Yes |
| **OpenCode / Claude Code** | Autonomous task execution | Runtime tool calls (grep, glob, read) | Yes |
| **pi-mono** | Agent platform / SDK | Session-based context | Yes |
| **rag-foundry-universal** | Code intelligence for production maintenance | Persistent AST graph + vector store | **No** |

The "No" in that last cell is not a limitation — it is the design. A system that never touches production code is one that can be trusted with full read access to production code.

---

## The intended use case: production maintenance assistance

The author's stated intent is a **PR assistant for production-level code maintenance**, aimed at working developers — not a code generator for non-coders.

The workflow it is designed to support:

1. **Nightly ingestion** — the repository is re-ingested on a schedule, keeping the graph current with the committed, known-good state of the codebase. The agent always reasons about stable ground truth, never about a half-edited working tree.

2. **Chat interface during PR review** — a developer opens a PR and can ask the system natural-language questions: "Is there anything that calls this function that I haven't updated?" "What's the precedent in this codebase for handling this error case?" "What did this module look like before this sprint's changes?"

3. **Proactive diff comments** — the system can run a fixed set of graph queries automatically when a PR is opened, and post findings as structured comments. Callers of changed functions. Modules with recent structural changes. Test files associated with modified paths. This is the *push* mode — surfacing what the developer didn't think to ask about.

4. **Tool for an agentic system** — the RAG is designed to be callable as a tool by a separate coding agent. The agent uses it to answer "what should I target?" before making any edits, and "what does the system look like before vs. after?" as a comparison mechanism. This gives an autonomous agent structural precision it cannot achieve through runtime file exploration alone.

---

## What makes the graph approach distinctive

**Structural queries that text search cannot answer.** "What calls `process_payment()`" done with grep returns all lines containing that string. Done with the call graph, it returns the actual runtime callers with their module context, call depth, and relationship type. These are different answers, and the graph answer is the correct one for impact analysis.

**Versioned snapshots for change comparison.** Because each nightly ingestion run is a distinct snapshot, the system can answer questions about *change over time* — not just "what is the code" but "what changed in the structural relationships around this module since last week." No existing coding tool offers this cleanly.

**Separation of reading from writing removes a category of risk.** An agent that can only read the codebase cannot accidentally break it. This makes the system safe to deploy with broad access to production repositories in ways that autonomous coding agents are not.

**Handles both code and documentation in one graph.** The Markdown ingestion means that ADRs, design documents, and module-level READMEs are first-class citizens in the same graph as the code itself. A query about why a module is structured a certain way can return answers from both the code structure and the documentation.

---

## For developers considering contributing or building on this

The codebase is Python throughout, using FastAPI for the service layer, PostgreSQL with `pgvector` for storage, and standard Python AST for code parsing. The services are independently deployable and communicate over HTTP. The Gradio UI provides a working reference client.

The most natural extension points are:

- **Additional language support** — the AST extraction currently targets Python; adding tree-sitter support for other languages would extend the graph to polyglot repos
- **GitHub App integration** — hooking ingestion and query into PR events via GitHub webhooks to enable the proactive diff-commenting workflow described above
- **Richer tool definitions** — exposing the graph's capabilities as a typed, well-described tool set that a coding agent can call with precision: `get_callers(fn)`, `get_dependencies(module)`, `diff_since_snapshot(module)`, `find_definition(symbol)`
- **Snapshot diffing** — making the versioned ingestion history queryable as structural diffs, not just point-in-time snapshots

---

## Current limitations and honest roadmap

This section is written at the author's request. Engineers trust projects more when the author is clear-eyed about what is incomplete than when documentation reads as though everything is perfect.

### What has not been tested enough yet

**Cross-repo and cross-machine validation.** The system has been developed and tested against a limited set of repositories on a single development machine. It has not been stress-tested across diverse repo sizes, structures, or dependency patterns. Edge cases in the AST parser, graph builder, and BFS traversal almost certainly exist and have not been found yet. Contributors who run it against their own repos and file issues will be doing genuinely useful work.

**The OCR abstraction layer.** The system is architected to support multiple OCR backends and uses Tesseract as the default. The abstraction layer for swapping in other OCR engines (for document ingestion) has been designed but not implemented or tested beyond Tesseract itself. It is forward-looking scaffolding, not a working plugin system yet.

**The general document RAG path.** The system can ingest regular documents and perform standard RAG over them, not just code repositories. This path works and is not singled out as less reliable than the code graph path — both are subject to the same overall caveat that the system has not been tested widely across diverse environments and repos. The document ingestion pipeline is powered by **Docling**, a universal document preprocessor that handles PDFs, DOCX, PPTX, XLSX, CSV, Markdown, and plain text files. Images are handled separately via Tesseract OCR. The full ingestion capability matrix is:

| Content type | Ingestion path | Graph | Query path |
|---|---|---|---|
| Python code | AST + canonical graph | CALL, DEFINES, IMPORT | Graph-aware RAG |
| Markdown (repo) | Section extraction | DEFINES | Graph-aware RAG |
| Markdown (upload) | Section extraction | DEFINES | Document RAG |
| PDFs | Docling → Markdown → chunks | flat | Document RAG |
| DOCX / PPTX / XLSX / CSV | Docling → chunks | flat | Document RAG |
| Text files | Chunking + embedding | flat | Document RAG |
| Images | Tesseract OCR → chunks | flat | Document RAG |

The distinction between graph-aware and flat document RAG reflects a structural difference, not a quality difference: code and structured Markdown have relationships worth traversing (call graphs, section hierarchies), while PDFs and office documents are treated as flat chunk sequences. Both paths use the same embedding and retrieval infrastructure.

### What needs real feature work

**LLM provider switching.** Currently the system is primarily built around Ollama for local inference. Switching to cloud-based LLMs (OpenAI, Anthropic, Google) requires more than a configuration change — the LLM service layer needs a cleaner provider abstraction with proper credential management. This is planned but not yet implemented smoothly.

**Reranker support.** The retrieval pipeline returns results ranked by vector similarity. Adding a reranker — a second-pass model that re-scores retrieved chunks for relevance to the specific query — would meaningfully improve answer quality, particularly for complex structural queries. The architecture could accommodate this, but no reranker integration exists yet.

**Polyglot support.** The AST-based code graph currently understands Python only. Extending to JavaScript, TypeScript, Go, Java, or other languages requires replacing the Python AST extractor with tree-sitter grammars per language. This is the single most significant gap for teams working in polyglot codebases, and it is real engineering work, not a configuration toggle.

### The hardware context

The entire system was designed and built on an Intel Core i7-8565U laptop with 8GB RAM and no GPU. This is a meaningful constraint to understand:

On the limitation side, it means GPU-accelerated embedding models, large local LLMs, and high-concurrency ingestion of very large repos have not been tested. Performance at scale is an open question.

On the positive side, it means the system was designed from the start to be lightweight. It runs on modest hardware without requiring a GPU or a beefy cloud instance. Teams that want to self-host this against private production repositories — which is the intended deployment model — do not need expensive infrastructure to get started. The architecture earns its keep on a laptop, which is a reasonable baseline for a self-hosted tool.

### Summary of what is production-ready vs. what is not

| Component | Status |
|---|---|
| Python AST graph ingestion | Working, limited cross-repo testing |
| Markdown / doc graph ingestion | Working |
| BFS graph traversal queries | Working |
| Vector similarity search | Working |
| Docling document ingestion (PDF, DOCX, PPTX, XLSX, CSV) | Working |
| Tesseract OCR ingestion (images) | Working |
| General document RAG | Working |
| Ollama (local LLM) integration | Working |
| Cloud LLM switching | Needs work |
| Reranker integration | Not implemented |
| OCR abstraction (multi-backend) | Scaffolded, not tested beyond Tesseract |
| Polyglot (non-Python) support | Not implemented |
| GitHub App / PR integration | Not implemented |

---

## Summary assessment

This is a **focused, well-scoped infrastructure project** with a clear point of view about what AI assistance in production codebases should look like. It is not trying to replace the developer. It is trying to give the developer something no existing tool offers: a persistent, structurally precise, queryable map of their codebase that an AI can reason over reliably.

The read-only constraint, the nightly ingestion discipline, the graph-over-vector-only approach, and the explicit targeting of PR review rather than autonomous code generation all reflect coherent design thinking about what production codebases actually need from AI tooling.

The gap between what this project does today and a full PR assistant is mostly integration work — GitHub webhooks, a chat UI wired to the query endpoints, and well-defined tool schemas for agent consumption. The hard part, the graph itself, is already built.

---

*Written by Claude (claude-sonnet-4-6), March 2026, based on repository README, architecture documentation, and an extended design conversation with the author covering the broader AI coding tools landscape, architectural tradeoffs, and the author's stated intent for the project. The limitations section reflects the author's own honest assessment of where the project stands.*
