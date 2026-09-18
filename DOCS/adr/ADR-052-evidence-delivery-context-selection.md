---
title: "ADR-052: Passage selection and final-context provenance"
date: 2026-09-17
type: adr
status: proposed
tags: [retrieval, evidence, context, generation]
related:
  - "[WP-R4 specification](/specs/005-production-correctness/issues/evidence.md)"
  - "[ADR-051 graph cache](/DOCS/adr/ADR-051-generation-aware-graph-cache.md)"
  - "[Verification record](/DOCS/test_results/2026-09-17-wp-r4-evidence-delivery.md)"
---

# Passage selection and final-context provenance

Issue [#167](https://github.com/sankar-ramamoorthy/rag-foundry-universal/issues/167).
Implementation is on `fix/wp-r4-evidence-delivery`; acceptance and merge pending.

## Decision under verification

`POST /v1/vectors/search-by-doc` accepts optional `query_vector`, `repo_id`,
and `ingestion_id`, and a bounded `k` (1?100). It materializes the filtered
artifact rows and orders by exact cosine similarity, stored ordinal, then
chunk ID. Without a query vector it orders by ordinal and chunk ID. This
bounds response rows and avoids approximate global ANN loss within an
artifact; database work still scales with that artifact's passage count.
It does not change embedding units or ingestion identity.

Repository retrieval resolves a ready generation before seed search, scopes
seed and supplementary passage queries to it, and verifies it again after
retrieval. Unavailable/building generations return 503; a changed generation
returns 409. This extends ADR-051's explicitly narrower graph-only decision.
The cache itself and ingestion publication mechanism are unchanged.

Fetch supplementary query-relevant passages for seeds as well as selected
graph artifacts. Keep stored `chunk_index` separate from `fetch_position`;
unknown stored ordinals remain null. Fetch requests report counts, not invented
ordinal ranges. Sort relaxed ANN results explicitly by descending score and
chunk ID. Within graph relation priority, rank query-term overlap with the
canonical ID before the existing deterministic order. This lexical preference
requires measured quality acceptance and does not claim semantic recall.

Assemble context once, returning text and selected whole chunks. Derive sources
and manifest from that same selection. The manifest includes a text SHA-256,
stored ordinal and fetch position. Simple-document RAG includes fetched
expansions and exposes the same manifest. Record reranker losses separately
from chunk limits and context budget losses.

## Budget contract

The deterministic conservative estimate is UTF-8 byte length, including source
labels and double-newline separators, rather than whitespace word count.
`token_count_method` identifies it as an estimate, not measured model tokens.
Skip oversized whole passages and continue considering later passages.

Context allowance is the minimum of the caller's `max_total_tokens` and
`CONTEXT_WINDOW_TOKENS - PROMPT_RESERVE_TOKENS - OUTPUT_RESERVE_TOKENS -
UTF8(query)`, floored at zero. Defaults are 8192, 1024 and 2048 respectively.
These are configured orchestration allowances, not discovery of the selected
provider's actual window or enforcement of its generation limit. Deployments
must align them with model policy, including fallbacks. A model-aware prompt
boundary check and oversized-query behavior remain review items before
claiming a complete end-to-end token guarantee.

## Scope and remaining evidence

Service HTTP/DB boundaries and model-used/fallback provenance stay intact.
No new embedding or reranker default is introduced. Existing artifact-versus-
subchunk persistence and pipeline-factory drift are not resolved by this change.

Payload and real PostgreSQL tests cover mechanics. An uncontaminated pinned
question set, matched-budget baseline, clean/noisy generation controls and
per-question failure attribution remain mandatory quality acceptance. Unit
success is not evidence that lexical selection improves real answer quality.
