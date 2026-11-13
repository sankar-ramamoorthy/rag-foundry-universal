---
title: "Open-Source Code RAG Systems — Reference Study Candidates"
date: 2026-11-12
type: landscape-study
status: proposed
project: RAG-FOUNDRY-UNIVERSAL
tags: [open-source, code-rag, competitive-study, hybrid-search, agent-tools]
aliases: ["Code RAG Competitor and Reference Landscape"]
authority: "Projects and capabilities discussed in conversation; verify actual implementation, licenses, benchmark claims and current maintenance before relying on them"
related: ["[[00-Strategy-Discussion-Index]]", "[[02-Retrieval-Strategies-and-Planning]]", "[[06-Agent-Use-Cases-and-Issue-Evaluation]]", "[[08-Experiments-Gates-and-Open-Decisions]]"]
---
# Open-Source Code RAG Reference Study

## Why review others now?

We have repeated failures in RAG-FOUNDRY-UNIVERSAL despite adding extraction, provenance and graph expansion. Rather than implement another planner from intuition, inspect working codebases that expose different approaches to symbol resolution, lexical + semantic retrieval, graph navigation and coding-agent tool integration. Feature descriptions are **claims requiring source verification**, not proof of quality.

## Candidates discussed

| Project | Link | Claimed/directed area of study | Evaluation caution |
| --- | --- | --- | --- |
| CodeRAG (galacticsurfer) | https://github.com/galacticsurfer/coderag | Exact-symbol + full-text + vector search, rank fusion, graph expansion, MCP | Verify implementation and stability, not only README |
| Code-Graph-RAG (vitali87) | https://github.com/vitali87/code-graph-rag | Tree-sitter, graph navigation, graph queries, agent access | Verify graph correctness and actual tracing capabilities |
| Code RAG (paulxiep) | https://github.com/paulxiep/code-rag | Intent-dependent routing, call-graph lookup, MCP | Examine classifier failures and fallback behavior |
| Treeweft | https://github.com/Treeweft/treeweft | Tree-sitter and graph search, coding agent workflow comparisons | Treat reported benchmarks as vendor claims until reproduced |
| RAG Your Code | https://github.com/skymanbp/rag-your-code | Simple code indexing/retrieval for an external agent | Test whether simplicity is an advantage against richer graph designs |

No project was selected for adoption or dependency integration. No current commits, licenses, or release versions were independently inspected in preparation for this note.

## Comparative architecture checklist

For each project, inspect and record:

1. Whether it separately indexes **defining symbols** and mere *mentions/usage*.
2. Whether source paths classify library implementation, tests, examples, documentation and generated files.
3. Whether query interpretation is deterministic, classifier-based, LLM-assisted, or absent.
4. Whether vector search is the first step or one branch of a hybrid retrieval plan.
5. Whether it exposes lexical/regex and exact-name lookup, and how it fuses candidate scores.
6. Whether the graph is built by parsing, language servers, heuristics, or an LLM; how unknown receiver types are represented.
7. Whether expanded implementation evidence survives token budgeting.
8. Whether iterative retrieval adapts to missing evidence.
9. Whether its agent integration exposes typed tools or only a single generated answer endpoint.
10. Whether it can pin repository revision/generation and handle incremental updates and deletion.
11. License, maintainability, deployment resources and version stability.
12. Measured benefits on **the same pinned issues** compared with grep/file-read baseline.

## Recommended comparison protocol

Use a single frozen repository snapshot and identical prompts. Record the raw retrieved defining nodes, supporting code ranges, graph paths, final evidence, tool calls, and wall-clock costs. Evaluate on both an explicit symbol/endpoint trace and a broad workflow/bug diagnosis. Do not interpret a fluent answer as evidence of correct retrieval.

The LightRAG question is a useful control, but a benchmark should also include unseen issues at pre-fix commits and at least one query requiring historical documentation, to detect overfitting to implementation-first retrieval.

## Decision boundary

The purpose is to learn which retrieval mechanisms are worth experimenting with inside existing RAG-FOUNDRY-UNIVERSAL boundaries, **not** to adopt a whole competing architecture or rewrite the stack. Reconcile findings with [[08-Experiments-Gates-and-Open-Decisions]] and the current ADRs before creating implementation issues.
