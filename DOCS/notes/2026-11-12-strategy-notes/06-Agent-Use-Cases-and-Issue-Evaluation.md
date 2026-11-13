---
title: "Practical Use — Repository Intelligence as a Coding-Agent Tool"
date: 2026-11-12
type: product-experiment
status: hypothesis
project: RAG-FOUNDRY-UNIVERSAL
tags: [coding-agents, github-issues, benchmarks, issue-localization, mcp, product-strategy]
aliases: ["Real-Issue Repository Intelligence Evaluation"]
authority: "Proposed evaluation program; no repository issue benchmark run authorized"
related: ["[[00-Strategy-Discussion-Index]]", "[[03-Evidence-Driven-Investigation-Loop]]", "[[08-Experiments-Gates-and-Open-Decisions]]"]
---
# Repository Intelligence as a Tool for Coding Agents

## Owner's practical-use challenge

Instead of judging only whether a standalone RAG query produces a plausible answer, **download an active open-source project, choose a real bug/issue, and see whether repository intelligence actually helps an agent understand the issue and locate a fix**.

Proposed product question: *Does RAG-FOUNDRY-UNIVERSAL improve diagnostic accuracy or reduce investigation effort for a coding agent compared with that agent's normal grep, file-read, shell and search tools?*

## Capability levels (discussion framing)

1. **Repository retrieval:** locate defining files/symbols, docs, test cases and source text.
2. **Repository investigation:** reconstruct call paths, lifecycle flows and likely root causes; disclose unresolved edges.
3. **Agent intelligence tools:** expose versioned, stable symbol/graph/evidence APIs to an external coding agent working on issues and changes.

Level 3 depends on credible Level 1 and Level 2, but need not imply a fully autonomous internal coding agent.

## Select an issue fixture carefully

- Prefer a real, reproducible issue with nontrivial but bounded scope and a known historical fix; start with a **closed issue and its pre-fix commit** for independent scoring, then use fresh active open issues as a prospective check.
- Ingest the *pre-fix* repository snapshot, not its fixed version. Freeze dependency/env assumptions where feasible.
- Hide solution patch, comments that reveal the fix, benchmark answer key and issue PR from the investigating agent.
- Keep the evaluator's reference patch and tests separate from agent-visible context (evaluation isolation; see ADR-054).
- Choose simple (single-file), intermediate (multi-module), complex (lifecycle/cross-module) examples; do not extrapolate broad performance from one case.
- Avoid choosing a repository merely because it is already familiar to the model or because the issue description names the exact target function.

## Experimental arms

| Arm | Agent access | What it tests |
| --- | --- | --- |
| A | Normal coding tools (grep, file reads, shell) | Genuine baseline |
| B | A + current RAG `/v1/rag` | Current incremental value (or cost) |
| C | A + exact symbol, lexical, ORIENT/TRACE and graph API tools | Value of structural tools without built-in loop |
| D | A + bounded adaptive investigation tool | Value of iterative evidence assistance |

Keep coding model, issue prompt, allowed external information, time/token budget, tool-call accounting, and pre-fix repository snapshot comparable. Randomize task order across issues; avoid giving one arm an answer revealed by another.

## Two-phase scoring

**Phase 1 — Diagnosis, before code changes:**

- File localization precision/recall and function localization.
- Grounded root-cause explanation and distinguishing symptom from cause.
- Correct execution/dependency path, with uncertain links labeled.
- Relevance of cited code and tests; correctness of assumptions.
- Exploration cost: source reads, tool calls, tokens, wall-clock and latency.
- Whether RAG provided information the baseline agent did not find quickly.

**Phase 2 — Fix assistance (only once Phase 1 is credible):**

- Patch success against held-out tests.
- Regression introduction, overbroad edits, and security concerns.
- Time to passing tests and use of citations in implementation reasoning.
- Reduction in search time without harming correct diagnosis.

This avoids confusing a weak patch-authoring model with a poor retrieval system.

## Candidate task types

- Trace a REST endpoint through application and persistence layers.
- Diagnose an ingestion lifecycle bug spanning error handling and state transitions.
- Locate the owner of a configuration/timeout mismatch.
- Find why a graph edge is unresolved across a class/receiver boundary.
- Find an existing regression test, or explain why it does not cover reported behavior.
- Estimate impact of changing a function (IMPACT/TRACE use case).

## Tool contract ideas, not approved APIs

`repository_inventory`, `resolve_symbol`, `resolve_route`, `lexical_search`, `semantic_candidates`, `graph_neighbors`, `find_path`, `read_node_text`, `get_generation`, `get_evidence_manifest`.

Every result should include repository and generation IDs, canonical symbol identity, source path/range, evidence role, confidence/uncertainty, and explicit failure/gap status. This could support MCP later, but protocol adoption should be evaluated against actual agent workflows; do not treat it as necessary now.

## Important design fork

Do agents need our internal RAG generation at all, or would **typed retrieval/navigation tools** be more useful? The question must be tested, not decided from architecture preference. An internal bounded loop might still be valuable for Gradio and direct RAG API users.

## Benchmark caution

Historical issue benchmarks (for example SWE-bench-style pre-fix tasks) are useful sources of reproducible fixtures but susceptible to answer leakage and model training exposure. Include locally constructed or freshly observed tasks, pre-registered scoring, and an evaluation isolation protocol.
