---
title: "CI-06 bounded delivery evaluation: protocol and acceptance criteria"
date: 2026-11-10
type: evaluation
status: frozen
summary: "Pre-registered before any delivery result was computed; development corpora only"
tags: [ci06, evaluation, delivery, discovery, issue-337, pr-339]
related:
  - "[Issue #337](https://github.com/sankar-ramamoorthy/rag-foundry-universal/issues/337)"
  - "[Independent review R4](/DOCS/audit/2026-11-10-ci06-pr339-independent-review.md)"
  - "[ADR-056 (proposed)](/DOCS/adr/ADR-056-embedding-input-contract.md)"
  - "[ADR-054: evaluation dataset isolation](/DOCS/adr/ADR-054-evaluation-dataset-isolation-and-generalization.md)"
  - "[E1 development manifest](/DOCS/evaluations/code-evidence-e1/manifest.json)"
  - "[WP-R4 questions](/DOCS/evaluations/wp-r4-questions.json)"
---

# CI-06 bounded delivery evaluation — protocol

Frozen before any delivery, discovery-for-questions, multilingual or long-query
result was computed. Implemented by `scripts/ci06_delivery_eval.py`. Development
data only: no held-out case, corpus or pin is read, and no deployed generation
is queried or rebuilt (ADR-054).

## Contracts compared

- **Legacy.** `heuristic-v1` units. Vectors encode the old client-cut input
  (800 characters, 400 words) with Ollama's default server truncation; the
  delivered passage is the full unit, as before CI-06.
- **New (repository path).** ADR-056 line windows, embedded strictly; a passage
  the serving model rejects is split exactly as the ingestion pipeline does.
- **New (upload path).** Fitted document heuristic (multilingual set only).

Model: `mxbai-embed-large:latest`, digest `468836162de7`, via Ollama; the
serving version is recorded with the results.

## Case sets

1. **Questions with expected statements:** the six E1 development cases
   (L1–L3 LightRAG at `4d0afc1`, F1–F3 foundry at `109f12d8`), scored on their
   frozen operation and dependency expressions; the eight WP-R4 questions
   (foundry at `3ba6a2f`), scored on their required substrings. Target texts
   are checked against the E1 manifest hashes where available.
2. **Multilingual documentation needles:** LightRAG documentation lines of 15–80
   characters that are at least half CJK and unique to one file; up to 150,
   seed 337.
3. **Long queries:** each question in set 1 followed by up to 1,600 characters
   of the code that precedes its primary target in the same file.

Each repository snapshot's ranked corpus is every artifact named by its cases
plus 600 random code artifacts (seed 337).

## Procedure

- **Discovery:** the primary target is discovered when any of its passages is
  among the top 20 passages by cosine similarity (production seed `top_k`).
- **Delivery (production-like):** seed documents in first-appearance order with
  their seed passages (at most 5 each), then every other artifact named by the
  case as an expanded document with its 3 best passages for the query (the
  production `search-by-doc` k). At most 50 passages, assembled by the
  production `assemble_context` with the 4,096-byte cap. Graph expansion is
  assumed to reach the named artifacts for both contracts alike. Sensitivity:
  5 passages per expanded document.
- **Expression credit:** a whitespace-normalized expression counts when it
  appears in a delivered passage from the same file as its expected artifact.
- **Long queries:** (a) legacy index with the legacy query cut, (b) legacy index
  with the new query handling (the state after deploying, before re-ingestion),
  (c) new index with the new query handling.
- **Multilingual:** an artifact-level hit when any passage from the gold file is
  in the top 5.

## Acceptance criteria

| ID | Criterion |
| --- | --- |
| D1 (primary) | New delivers at least as many expected expressions as legacy, minus 5% of all expected expressions (rounded up). |
| D2 | No case loses more than half of the expressions legacy delivered for it. |
| D3 | Primary targets discovered: new ≥ legacy − 1 case. |
| D4 | Multilingual hit@5: each new path ≥ legacy − 5% of queries (rounded up). |
| D5 | Long-query discovery: (b) ≥ (a) − 1 case and (c) ≥ (a) − 1 case. |

A failed criterion is reported as failed and escalated to the owner. These
cases are not used to tune budgets in this PR.

## Not measured

Generated answers and their quality, real graph expansion and ranking with
competing documents beyond the sampled corpus, the deployed stack, and
held-out data. The proxy measures evidence survival, not answer correctness.
