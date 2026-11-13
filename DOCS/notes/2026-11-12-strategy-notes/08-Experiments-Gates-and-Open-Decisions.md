---
title: "Adaptive Retrieval — Evaluation Gates, Sequence, and Open Decisions"
date: 2026-11-12
type: experiment-roadmap
status: proposed
project: RAG-FOUNDRY-UNIVERSAL
tags: [experiment-design, acceptance-criteria, evaluation-isolation, governance, decision-gates]
aliases: ["Adaptive Retrieval Experimental Plan"]
authority: "Proposed sequence only; must reconcile existing roadmap, ADRs, issue and milestone before execution"
related: ["[[00-Strategy-Discussion-Index]]", "[[01-Evidence-and-Failure-Analysis]]", "[[02-Retrieval-Strategies-and-Planning]]", "[[03-Evidence-Driven-Investigation-Loop]]", "[[06-Agent-Use-Cases-and-Issue-Evaluation]]"]
---
# Evaluation Gates, Sequencing, and Open Decisions

## Governing constraints

- **No code without an issue; no issue without a milestone.** Use branch + PR for project changes.
- Do not silently mutate production, re-ingest, replace models, move databases, or run held-out experiments.
- First reconcile with November 10 audit, independent review, existing decision gates, E1 work and architecture ADRs.
- Preserve baseline evidence separately from prototypes. Do not overwrite failed-query artifacts.
- Every experimental conclusion must specify exact code revision, corpus generation, question text, scope, tool configuration, scoring procedure, and any model/version used.

## What is already in hand

1. November 11 Linux self-repo smoke response (correct answer, documentation-dominated context).
2. November 11 self-repo endpoint-trace response (abstention, documentation-only final context).
3. Gradio ingestion-lifecycle failure screenshot (no complete trace available).
4. Claude's two LightRAG controls and reported exhaustive rank probe (raw files kept locally/ignored; need preservation under approved documentation process).
5. User-supplied DeepWiki answer excerpts (reference candidates; not perfect ground truth).
6. Existing November 10 audit, which cautions that adaptive investigation inherits generation consistency, structural completeness, and source-fidelity problems.

## Proposed staged experiments — one change at a time

| Gate | Comparison | Decisive evidence | If it fails |
| --- | --- | --- | --- |
| G0 Baseline preservation | Freeze existing queries, outputs and ranking probe | Reproducible current behavior + generation identity | Stop; do not attribute changes |
| G1 Source/index presence | Verify definitions, vector chunks, role/path metadata, graph links | Relevant code indexed at exact generation | Investigate extraction/indexing first |
| G2 Metadata ablation | `source_type`, implementation `doc_type`, source-role/path preferences | Better implementation recall without losing needed tests | Separate docs contamination from examples/tests |
| G3 Candidate strategy | Vector vs lexical vs exact symbol vs fused | Defining-symbol recall@k, rank, latency | Plan graph/anchor resolution, not larger context alone |
| G4 Graph connectivity | Endpoint/receiver paths, unresolved placeholders | Verified edges and reason for unresolved links | Improve extractor/resolver with evidence |
| G5 Evidence survival | Same candidates, varied context allocation | Required implementation survives final context | Fix passage selection/context budget policy |
| G6 Generator isolation | Qwen3:4b vs stronger generator, identical curated source | Causal accuracy and citation validity | Address reasoning separately |
| G7 Bounded loop | Static one-shot vs 2–3 evidence-driven rounds | Coverage/correctness gain vs cost/latency | Reject loop complexity if no improvement |
| G8 Agent utility | Normal tools vs normal tools + RAG/structural tools | Better issue localization and/or less exploration | Reconsider product positioning |
| G9 Storage (conditional) | PostgreSQL vs alternatives on needed graph workload | Meaningful bottleneck reduction with acceptable ops risk | Retain PostgreSQL |

The order is intentionally **causal**, not a feature roadmap. A simple candidate strategy can be a win without adding a loop. An LLM classifier is not mandatory for deterministic queries.

## Required held-out evaluation questions

- **Q1 Self-repo endpoint trace:** supplied November 11 prompt; answer key must identify actual route handler, orchestrator functions, HTTP boundary, supporting code, and gaps.
- **Q2 LightRAG endpoint trace:** supplied November 11 long prompt; score `query_text`, `aquery_llm`, retrieval helpers, `chunks_vdb.query` and unresolved dispatch links by source excerpts; avoid blindly adopting DeepWiki as ground truth.
- **Q3 Ingestion lifecycle:** capture the exact Gradio prompt and full retrieval trace if available; freeze a separate implementation-verified answer key.
- **Q4–Q6 Real issue cases:** one simple, one cross-module and one lifecycle bug at pinned pre-fix snapshots, with fix and tests sealed from the investigator.
- **Q7 Non-implementation control:** historical ADR rationale or test-coverage question to detect over-filtering of documentation/tests.

## Success metrics

**Candidate stage:** relevant defining-node recall@5/20/100, first relevant rank, classification contamination, unique target files and symbols.

**Graph stage:** verified path edge recall/precision, unresolved-edge identification, placeholder fraction with explicit denominator, no invented call edges.

**Delivery stage:** percent of mandatory proof passages present in *final* context; redundant token spend; over-budget pruning reasons; generation consistency.

**Answer stage:** statement-to-source grounding, complete/partial coverage, calibrated abstention, root-cause correctness and misleading confidence.

**Practical agent stage:** file/function localization, diagnosis success, investigation latency, tool/token cost, patch correctness (only later).

No numerical pass threshold was approved today. Define thresholds **before** viewing candidate results, and distinguish regression guardrails from aspirational targets.

## Decision register — questions, not answers

| Decision ID | Open question | Dependency |
| --- | --- | --- |
| D1 | Is the product mainly autonomous repository Q&A, agent tool infrastructure, or both? | G8 |
| D2 | Should retrieval planning be deterministic, classifier-based, LLM-assisted, or tiered? | G2–G3, G7 |
| D3 | Which retrieval tools/filters must be available as stable APIs? | Inventory of existing tools/ADRs |
| D4 | How do we formalize sufficient evidence across trace, workflow and diagnosis questions? | G4–G5, obligation rubric |
| D5 | Who owns the investigation loop: internal service or external coding agent? | G7–G8 |
| D6 | Which embedding/generator/reranking changes justify hardware cost? | G3/G6 and model ablations |
| D7 | Are graph placeholder edges materially limiting real issue investigation? | G4, real issues |
| D8 | Is a graph database migration justified? | G9 only after workload definition |
| D9 | How do we enforce consistent committed generation across tools/iterations? | Audit findings and runtime proof |
| D10 | How do changes fit with E1 and the existing roadmap without parallel solutions? | Roadmap/ADR/issue reconciliation |

## Documentation handoff guidance

The owner reported that Claude wrote an uncommitted `DOCS/notes/20261111-code-intelligence-retrieval-failure-evidence.md` and local `_raw/20261111-code-intelligence-control/` artifacts indexed in `raw-index.json`. That content is **not duplicated verbatim** here because the draft and raw captures were not attached. Before committing this package, reconcile overlapping claims with that source, preserve date/status attribution, link via OKF-conformant paths where required, and avoid creating a second canonical failure report.

## Practical next step proposed, not authorized

Create a **review-only architectural discussion** comparing query planning, multi-strategy retrieval, source authority, and bounded investigation against existing shipped capabilities and the November audit. Build a pre-registered experiment plan under an appropriate existing milestone, then authorize one narrowly bounded read-only baseline/ablation at a time. No production implementation is implied by saving these notes.
