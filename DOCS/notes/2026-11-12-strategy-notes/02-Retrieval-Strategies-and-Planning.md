---
title: "Adaptive Retrieval — Strategy Selection and Search Planning"
date: 2026-11-12
type: architecture-exploration
status: hypothesis
project: RAG-FOUNDRY-UNIVERSAL
tags: [retrieval-strategy, query-planning, graph-traversal, symbol-search, hybrid-search]
aliases: ["Query-Aware Retrieval Planner"]
authority: "Exploratory design; no approved planner architecture"
related: ["[[00-Strategy-Discussion-Index]]", "[[03-Evidence-Driven-Investigation-Loop]]", "[[04-Metadata-and-Evidence-Authority]]", "[[08-Experiments-Gates-and-Open-Decisions]]"]
---
# Retrieval Strategies and Planning

## Change in framing

Current dominant code-query flow, per inspection reports: `natural-language query → embedding/vector seeds → keyword-rule graph expansion → context allocation → generation`. Several retrieval and deterministic structural capabilities exist, but the normal `/v1/rag` path does not reliably select among them based on evidence needs.

**Hypothesis:** Planning should represent *what must be established* and *which retrieval actions are most promising* rather than locking each question into one fixed category.

## Retrieval strategy repertoire (candidate capabilities)

| Strategy | Input anchor | Primary output | Typical use | Limitations |
| --- | --- | --- | --- | --- |
| Exact symbol/route/path lookup | `POST /v1/rag`, `LightRAG.aquery`, file path | Defining nodes and source locations | Explicit code identity | Aliases, overloads, route indirection |
| Lexical/full-text search | Identifier, exception, constant, error string | Matching source snippets | String-level localization | Synonyms and implicit behavior |
| Semantic/vector search | Natural-language concept | Broad candidates | Fuzzy discovery | Tests/docs/examples can outrank defining code |
| Neighborhood BFS | Known graph node | Callers/callees within hop budget | Who calls / is called by X? | Branching and unresolved edges |
| Path-oriented DFS | Entry node or suspected flow | Focused sequences | Follow a likely execution path | Can follow misleading branches |
| Bidirectional structural search | Start/end anchors | Candidate connecting paths | Endpoint to storage operation | Depends on accurate relationship orientation |
| Heuristic or A*-like prioritization | Goal + graph frontier | Ranked next edges/nodes | Complex investigation | Similarity heuristics not guaranteed admissible; avoid A* optimality claims |
| Structural inventory / ORIENT | Repo and generation | Modules, routes, service facts | Starting map and repository overview | Inventory need not encode dynamic runtime behavior |
| Historical/document retrieval | ADR or why-question | Design context | Rationale, changes, decisions | May be stale authority for present behavior |
| Test/example search | Symptom or expected behavior | Repro and behavioral assertions | Bug fixing and regressions | Example usage does not prove implementation internals |

These are search primitives, not ten separate product services.

## Plan as evidence requirements

Example input: `Why does repository deletion sometimes leave stale vectors?`

```yaml
intent: diagnose_behavior           # illustrative, not a proposed runtime schema
repository_scope: selected_repo
hard_constraints:
  - committed_generation
  - authorization_scope
evidence_obligations:
  - deletion_entry_point
  - repository_state_transition
  - vector_cleanup_operation
  - error_and_retry_behavior
  - relevant_tests
initial_tools:
  - structural_inventory
  - lexical_search
  - semantic_search
soft_preferences:
  - role: implementation
  - role: tests
stop_condition: evidence_obligations_assessed
```

For `Where is rag_endpoint?`, a deterministic lookup may finish immediately. For `What happens when a small repo is ingested?`, the system may need entry-point discovery and an investigative walkthrough. **Do not demand one mutually exclusive intent label** for a multifaceted question.

## Classifier / LLM planning policy to test

1. **Deterministic first for high-precision anchors:** explicit file names, `Class.method`, route strings, known symbols, cited stack frames, and exact error text. Verify against indexed nodes; never hallucinate a resolution.
2. **Lightweight evidence-needs classification:** implementation, workflow, tests, documentation, history, inventory, and combinations thereof. Use multiple labels or obligations rather than one fixed category.
3. **Optional LLM planner for ambiguity:** broad workflow questions, root-cause hypotheses, mixed evidence needs. Treat output as a *proposal* that tools verify.
4. **Fallback and escalation:** if exact lookup fails, widen lexical/semantic search; if semantic candidates are poor, switch to structural anchors; if initial context is insufficient, investigate additional obligations.
5. **No unbounded reasoning requirement:** not every question needs an LLM classifier or repeated search.

## What to score during planning

- Whether selected tools are appropriate for the query.
- Whether hard constraints were respected throughout.
- Whether top-ranked candidates contain defining implementation rather than only mentions.
- Whether the planner changed strategy for a defensible reason.
- Whether newly explored nodes connect to the stated question.
- Whether the planner terminated without unnecessary tool calls.

## Search-algorithm analogy: useful, but not literal

The owner compared this to recognizing whether BFS, DFS or A* is appropriate. This is a strong framing for **policy selection** and **frontier management**. Do not assume shortest-path optimality of graph queries is equal to finding the best explanation. Call confidence, source authority, recency, causal relevance and evidence coverage are not simple additive distances.

## Architecture boundary to preserve

Expose composable retrieval operations (symbol resolve, lex search, vector candidates, graph neighbors, node-text fetch, generation check) behind a tool/API contract. Both a built-in iterative investigator and an external coding agent should be able to use the same operations. This avoids parallel implementations and permits changing the planner without changing the database engine.

See [[03-Evidence-Driven-Investigation-Loop]] for iteration and [[08-Experiments-Gates-and-Open-Decisions]] for experiment order.
