---
title: "WP-R4 frozen quality protocol"
date: 2026-09-17
type: evaluation
status: proposed
tags: [retrieval, evaluation, evidence]
related:
  - "[Questions](./wp-r4-questions.json)"
  - "[Quality methodology](/DOCS/audit/08-RAG-Quality-Evaluation-Methodology.md)"
  - "[Verification](/DOCS/test_results/2026-09-17-wp-r4-evidence-delivery.md)"
---

# WP-R4 frozen quality protocol

Freeze the eight questions in [wp-r4-questions.json](./wp-r4-questions.json)
before executing any query. They revalidate candidates 1, 2, 3, 4, 7, 10, 11
and 12 against source revision `3ba6a2f4cec4d3e0724859d70aeff98bb7f7880f`.
Candidate 11 now names `execute_traversals_from_seeds_detailed`, where the
ranking implementation currently lives. No TS/TradeForge coverage is claimed.

Corpus: 54 original Python files (341759 bytes), exported byte-for-byte from
that revision under `rag_orchestrator/src`, `shared/embedders`,
`ingestion_service/src/core/codebase` and `ingestion_service/src/core/extractors`.
No DOCS, tests, question sets, audit reports or generated answers are ingested.
This is a curated real-source subset, not a whole-repository benchmark.
Retain per-file SHA-256 and aggregate manifest hash with run output.
The corpus revision deliberately differs from the retrieval runtime revision;
answers describe the pinned corpus, never the newer runtime behavior.

Use local isolated PostgreSQL and actual ingestion/vector HTTP services,
mxbai-embed-large:latest with recorded digest, and an explicitly selected
existing generation model with recorded digest/provenance. Freeze runtime and
ground-truth commits independently before querying. No reranker is enabled.

Arms: legacy runtime, WP-R4 runtime, and a legacy-retrieval control using the
same conservative context allowance as WP-R4. Record top-k, document/passage
caps, context bytes and estimate, model-used/fallback, latency, prompt and
manifest. Any model fallback makes that pair non-comparable until repeated
with the same model. Record all failures; do not tune questions after results.

For each question, verify index presence, seed discovery, graph discovery,
document cap, passage selection, chunk limits, rerank and final prompt
survival. Grade the actual answer for rubric coverage, unsupported claims and
source attribution. Required substrings are passage diagnostics, not a
substitute for reading the answer. Run clean-context generation from the
original source and a noisy-context control under matched allowances; compare
failures to distinguish retrieval from generation. Keep every raw prompt and
answer. Report remaining failures and controls without claiming broad quality
improvement from unit tests or aggregate success alone.

Simple-document expansion is covered separately by payload tests; this frozen
source-only set cannot establish document answer quality or cross-project
quality generalization. Deployment remains a separate gate.
