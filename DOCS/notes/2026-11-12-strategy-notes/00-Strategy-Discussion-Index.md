---
title: "RAG-FOUNDRY-UNIVERSAL — Adaptive Retrieval Strategy Discussion Index"
date: 2026-11-12
created: 2026-11-12
type: discussion-index
status: raw
project: RAG-FOUNDRY-UNIVERSAL
tags: [rag-foundry-universal, code-intelligence, retrieval-strategy, architecture, obsidian, brainstorm]
aliases: ["November 12 Retrieval Strategy", "Adaptive Repository Investigation Index"]
authority: "Discussion record and architectural hypotheses; no design decision or implementation authorization"
related:
  - "[[01-Evidence-and-Failure-Analysis]]"
  - "[[02-Retrieval-Strategies-and-Planning]]"
  - "[[03-Evidence-Driven-Investigation-Loop]]"
  - "[[04-Metadata-and-Evidence-Authority]]"
  - "[[05-Models-Embeddings-and-Reranking]]"
  - "[[06-Agent-Use-Cases-and-Issue-Evaluation]]"
  - "[[07-Graph-Storage-and-Engine-Decisions]]"
  - "[[08-Experiments-Gates-and-Open-Decisions]]"
  - "[[09-Open-Source-Code-RAG-Reference-Study]]"
  - "[SCIP semantic enrichment and graph evidence addendum](./2026-11-12-scip-semantic-enrichment-and-graph-evidence-strategy.md)"
  - "[Architectural challenge and recommendation](./2026-11-12-repository-intelligence-architecture-challenge.md)"
  - "[Proposed falsification experiments](/DOCS/evaluations/2026-11-12-repository-intelligence-strategy-experiments.md)"
  - "[Matched retrieval-mechanism diagnostics](/DOCS/test_results/2026-11-12-retrieval-mechanism-diagnostics.md)"
  - "[Evidence planning, context capacity and multi-pass processing](./2026-11-12-evidence-planning-context-budget-and-multipass.md)"
---
# Adaptive Retrieval Strategy — Discussion Index

> [!important] Status and scope
> These notes capture the owner's November 12 architectural conversation, informed by November 11 live testing and Claude's reported diagnostic work. They are **not** ADRs, accepted requirements, completed experiments, or permission to change code, configuration, storage, production deployment, or the ingested corpus. Observations, external reports, interpretations, and hypotheses are kept separate.

## Why this discussion matters

RAG-FOUNDRY-UNIVERSAL has developed graph extraction, canonical identity, structural inventory (ORIENT), TRACE/IMPACT, provenance, vector search, and evidence diagnostics. Nevertheless, questions about real implementation frequently retrieve documentation about the code, example scripts, or test reports instead of the implementation. The central question is no longer merely how to add more graph expansion: **how should a repository intelligence system choose, execute, assess, and revise its evidence-gathering strategy?**

The owner raised four linked ideas:

1. Select among multiple retrieval strategies (analogous to choosing BFS, DFS, bidirectional search or heuristic/A*-like exploration).
2. Let a deterministic classifier or LLM assess what evidence is needed and which metadata restrictions or preferences apply.
3. Evaluate the retrieved results, and loop only when important evidence gaps remain; a fixed single-shot retrieval is not convincing for complex queries.
4. Judge practical utility using real coding agents and open-source issues rather than relying solely on general repository Q&A.

Additional discussion: consider stronger embedding/generation models and rerankers, existing source classifications, repository navigation maps, and whether new graph databases (HelixDB, Grafeo, SurrealDB, Apache AGE, Neo4j) are necessary. No database choice was made.

## Reading map

The latest [evidence-planning and context discussion](./2026-11-12-evidence-planning-context-budget-and-multipass.md)
captures query understanding, evidence assessment, the 4,096-byte restriction,
larger-context versus multi-pass experiments, and the local-inference questions.
It includes a restart point and preserves the owner's exploratory stance;
these follow-up experiments have not been run or approved.

**Latest clarification:** diagnose retrieval, navigation and evidence delivery on
the known failures before choosing an architecture. The
[matched retrieval-mechanism diagnostics](/DOCS/test_results/2026-11-12-retrieval-mechanism-diagnostics.md)
record actual same-corpus ranking comparisons, graph lookups and a source-based
study of Code-Graph-RAG and paulxiep/code-rag. The broader product investigation
below is deferred as the immediate next step.

For the subsequent independent strategy review, start with the
[architectural challenge and recommendation](./2026-11-12-repository-intelligence-architecture-challenge.md)
and its [proposed falsification experiments](/DOCS/evaluations/2026-11-12-repository-intelligence-strategy-experiments.md).
These challenge the discussion hypotheses below. The owner selected coding-agent
task completion as the primary outcome, with standalone repository Q&A secondary;
the architecture recommendation remains proposed and experiments are unexecuted.

| Note | Focus | Key question |
| --- | --- | --- |
| [[01-Evidence-and-Failure-Analysis]] | What failed in November live tests, with provenance and limits | What have we actually established? |
| [[02-Retrieval-Strategies-and-Planning]] | Retrieval repertoire, planning, algorithm analogies | What should we search, and how? |
| [[03-Evidence-Driven-Investigation-Loop]] | Evidence ledger, bounded iterative workflow | When should retrieval continue or stop? |
| [[04-Metadata-and-Evidence-Authority]] | `source_type`, `doc_type`, graph node types, provenance | What should be filtered, preferred or retained? |
| [[05-Models-Embeddings-and-Reranking]] | Embedding/reranking/model comparisons | Which model changes actually help? |
| [[06-Agent-Use-Cases-and-Issue-Evaluation]] | Coding-agent tool use, real issues, scoring | Does our system improve engineering work? |
| [[07-Graph-Storage-and-Engine-Decisions]] | Storage maturity and separable traversal interface | Is a new database justified? |
| [[08-Experiments-Gates-and-Open-Decisions]] | Experimental sequencing, acceptance gates and governance | What do we test before designing or coding? |
| [[09-Open-Source-Code-RAG-Reference-Study]] | Comparison candidates and benchmarking | What can we learn from existing code-RAG systems? |
| [SCIP semantic enrichment and graph evidence addendum](./2026-11-12-scip-semantic-enrichment-and-graph-evidence-strategy.md) | Optional SCIP enrichment, relationship evidence and evaluation gates | Can semantic resolution improve TRACE, IMPACT and EXPLAIN while preserving one canonical graph? |

## Governing design tension

**Possible product framing A:** A RAG endpoint that answers repository questions autonomously.

**Possible product framing B:** A *repository investigation service* that supplies exact lookup, structural navigation, semantic/lexical discovery and evidence to an external coding agent. A bounded built-in investigator can reuse those same tools for Gradio/API users.

The owner leaned toward practical agent utility, but this framing has **not** been formally decided.

## Existing project references

- [November 10 code-intelligence architecture audit](/DOCS/audit/2026-11-10-code-intelligence-architecture-audit.md) — static audit with source and synthetic probes, not a live release test.
- [November 10 full vision and strategic roadmap](/DOCS/notes/20261110-full-vision-and-strategic-roadmap.md) — raw vision, explicitly not a roadmap decision.
- [ADR-045 hybrid vector + graph RAG](/DOCS/adr/ADR-045-hybrid-vector-graph-rag.md).
- [ADR-052 evidence delivery](/DOCS/adr/ADR-052-evidence-delivery-context-selection.md).
- [ADR-053 source authority and provenance](/DOCS/adr/ADR-053-source-authority-provenance-model.md).
- [ADR-054 evaluation isolation](/DOCS/adr/ADR-054-evaluation-dataset-isolation-and-generalization.md).
- [ADR-055 node-text read endpoint](/DOCS/adr/ADR-055-node-text-read-endpoint.md).
- [November 11 retrieval failure note — reported local draft](/DOCS/notes/20261111-code-intelligence-retrieval-failure-evidence.md). Its existence was reported by Claude but the source file was **not supplied** for independent inspection here.
- [Retrieval technique decision gates](/DOCS/audit/09-Retrieval-Technique-Decision-Gates.md).

> [!note] Linking
> `[[...]]` links refer to sibling notes in this package and work as Obsidian wikilinks when placed in the same vault folder. Repository-relative standard Markdown paths above are contextual pointers, not verified links in this export. File names can be adapted to project conventions before a documentation PR.

## No decision was made

Do not treat these notes as authorization for an LLM classifier, a new investigation loop, a database migration, a model change, or an issue/PR. Before implementation: reproduce findings, reconcile existing roadmap/ADRs and issues, select a milestone, create an issue, and run controlled experiments.
