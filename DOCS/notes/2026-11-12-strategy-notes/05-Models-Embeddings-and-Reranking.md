---
title: "Embeddings, Rerankers, and Generators — Isolating Model Contribution"
date: 2026-11-12
type: experiment-design
status: hypothesis
project: RAG-FOUNDRY-UNIVERSAL
tags: [embeddings, model-evaluation, reranking, inference, retrieval-quality]
aliases: ["Better Models Versus Better Retrieval"]
authority: "Proposed comparisons; no new model measurements in this discussion"
related: ["[[01-Evidence-and-Failure-Analysis]]", "[[02-Retrieval-Strategies-and-Planning]]", "[[08-Experiments-Gates-and-Open-Decisions]]"]
---
# Better Embedders and Models?

## Question to answer experimentally

Could stronger embeddings or a stronger generation model overcome the observed code-evidence failures? **Possibly partially; evidence is insufficient to justify a model migration.** Separate candidate recall from reasoning quality.

## Current deployment context

- RAG query response reported `model_used: ollama/Qwen3:4b`, no fallback.
- Prior project configuration has used `mxbai-embed-large` (1024 dimensions) for repository embeddings. Confirm actual indexed model/version and vectors' generation before claiming a live-model comparison.
- Target LightRAG symbols reportedly ranked 329th–7,861st among 77,625 chunks for variants of a source-tracing query. Those are rank-probe results, not official embedding benchmark scores.

## Four independent hypotheses

1. **Embedding mismatch:** general semantic similarity prioritizes texts *describing* query behavior (docs, tutorials, test cases) over defining implementation.
2. **Candidate discovery architecture:** even a better embedder may still rank the right symbol below `k=5`; lexical/exact search might be the larger gain.
3. **Reranker limitation:** better reranking can reorder a candidate pool but cannot select a function ranked outside that pool unless first-stage recall improves.
4. **Generation limitation:** a small generator may misread complex call paths even after the right sources are provided. This is not yet isolated by existing tests.

## Minimum viable model ablation

Hold repository commit, ingestion generation, question, top-k/candidate budget, and scoring rule fixed. Where a different embedder requires re-embedding, use a **separate offline index**, never silently mutate production.

| Arm | Variable | What it isolates |
| --- | --- | --- |
| E0 | Existing vectors + current vector-only selection | Production baseline |
| E1 | Existing vectors + lexical/symbol fusion | Search design without model replacement |
| E2 | Alternative embedder, fresh controlled index | Representation quality |
| E3 | Reranker over identical large candidate set | Ordering improvement |
| E4 | Qwen3:4b given curated, verified source | Baseline model reasoning with retrieval removed |
| E5 | Stronger generator given *identical* curated source | Generation model contribution |

Do **not** compare answers from model A with short context and model B with enriched context and call the difference a model win. Keep evidence identical when testing generation.

## Evaluation metrics

- Recall@5/20/100 of pre-registered relevant **defining** symbols.
- First relevant implementation rank, mean reciprocal rank (MRR), source-role contamination.
- Verified call-edge coverage and unresolved-edge rate.
- Final-context inclusion and statement-level citation coverage.
- Answer correctness, abstention calibration and hallucinated edges.
- P50/P95 latency, peak memory, model/API costs, and CPU/GPU feasibility on the deployment host.

## Avoid premature commitments

Potential models and code-specific embedders should be selected from documented hardware constraints and a reproducible evaluation rather than named as winners here. Query expansion or a stronger LLM must not substitute for exact code identity or reliable source evidence.
