---
title: "ADR-056: Embedding-input contract — stored passages are the exact model input"
date: 2026-11-10
type: adr
status: proposed
tags: [adr, embedding, chunking, incremental-ingestion, ci06, issue-337]
related:
  - "[Issue #337](https://github.com/sankar-ramamoorthy/rag-foundry-universal/issues/337)"
  - "[CI-06 investigation](/DOCS/audit/2026-11-10-ci06-embedding-input-coverage-investigation.md)"
  - "[CI-06 verification](/DOCS/test_results/2026-11-10-ci06-embedding-input-coverage-verification.md)"
  - "[November 10 audit, CI-03 and CI-06](/DOCS/audit/2026-11-10-code-intelligence-architecture-audit.md)"
  - "[ADR-040: artifact-level embedding](/DOCS/adr/ADR-040-code-intelligence-embedding-strategy.md)"
  - "[ADR-041: code artifact persistence](/DOCS/adr/ADR-041-code-artifact-persistence-embedding-strategy.md)"
  - "[Incremental ingestion lineage spec](/specs/006-incremental-ingestion-lineage/spec.md)"
---

# ADR-056: Embedding-input contract

**Status: Proposed (2026-11-10).** Implemented on branch
`fix/337-ci06-embedding-input-coverage` for review. Not deployed. Acceptance is
the owner's decision at PR review.

Roadmap phase: Phase 6 correctness follow-up (CI-06, linked to CI-03).

## Context

The [CI-06 finding](/DOCS/audit/2026-11-10-code-intelligence-architecture-audit.md)
showed that stored passage text could be absent from every embedding input. The
[investigation](/DOCS/audit/2026-11-10-ci06-embedding-input-coverage-investigation.md)
measured about 10–12% of non-whitespace artifact text missing from every input
on two development corpora. It found two layers of silent truncation: the client
cut inputs to 800 characters, and Ollama cut inputs beyond the model's 512-token
context unless told not to.

Chunking and embedding had no shared size contract. Chunk sizes came from a
length heuristic whose sentence/paragraph units were unbounded; the embedder
then discarded whatever did not fit.

## Decision

1. **Invariant.** A stored passage (`vector_chunks.chunk_text`) is the exact,
   complete text the embedding model encodes. Neither the client nor the server
   may shorten it silently.
2. **One contract module.** `shared/embedders/input_contract.py` owns the
   budgets (800 characters; 480 by a conservative token estimate) and the
   contract identifier. Chunkers size passages to it; embedders do not trim.
3. **Repository artifacts** are chunked into exact line windows: verbatim,
   in-order slices that together cover the whole artifact, ending on line
   boundaries, repeating up to 100 characters of whole lines between windows.
4. **Other text** (document uploads) keeps its existing strategy selection, but
   every unit is split to fit the budgets. Its granularity is otherwise unchanged
   because no document-RAG evaluation was run for this decision.
5. **Embedder.** Ollama requests set `truncate: false`. An over-context input is
   isolated and, as a last resort, embedded with server truncation; that vector
   records `source_metadata.embedding_input.truncated = true` and a warning is
   logged. Every vector records the contract identifier.
6. **Reuse identity (CI-03 link).** The chunking version (`budgeted-v2`) and the
   embedding version (`<provider>:<model>:exact-input-v2`) both change. The
   existing all-or-nothing gate in the
   [incremental lineage spec](/specs/006-incremental-ingestion-lineage/spec.md)
   therefore re-embeds every artifact of a generation built under the old
   contract, once. Later generations under the same contract reuse normally.
   Any future change to a budget or to input handling must bump the contract.

## Alternatives considered

Measured in the [verification](/DOCS/test_results/2026-11-10-ci06-embedding-input-coverage-verification.md):

| Option | Outcome |
| --- | --- |
| Remove embedder truncation only | Full character coverage, but hundreds of inputs exceed 512 tokens, so Ollama would truncate them silently instead. Rejected. |
| Raise the character budget (1,000–1,500) | Fewer passages, but more inputs exceed 512 tokens; at 1,500 characters 18% of sampled code windows and 8% of documentation windows hit it. Rejected. |
| Character budget alone at 800 | Still exceeds 512 tokens on punctuation-dense tables and CJK text. Rejected in favor of the added token estimate. |
| Fit legacy heuristic units (option 4 applied to code) | Fixes coverage and discovery of previously missing text, but controls ranked consistently worse and it needs about 17% more code passages than legacy. Kept only for document uploads. |
| Line windows at 400–500 characters | 400 was best on the needle evaluation but needs ~1.8× the vectors, and halves evidence per passage while downstream passage caps are counts. 500 behaved worse than 400 and 800 on one corpus's controls, so the size effect is near the noise floor. Deferred. |
| Exact model tokenizer in the chunker | Would need a model-specific vocabulary in production code. The estimate gave zero overflows on both corpora, and overflow is still recorded explicitly. Deferred. |

## Consequences

- Coverage of artifact text in embedding inputs goes from about 88–90% to
  complete on the measured corpora. Passages that were previously undiscoverable
  by vector search become findable; see the verification for measured effects and
  the small control-query regression on one corpus.
- Fewer passages than legacy on both corpora (−22.5% and −4.9%).
- Every repository's next ingestion after deployment re-embeds everything, once.
  Vectors of the two contracts are never mixed within a generation.
- Passage text for repository artifacts is now verbatim, preserving indentation
  and whitespace that the sentence/paragraph strategies normalized.
- Queries longer than 800 characters are no longer cut by the client; overflow
  past 512 tokens follows rule 5.
- ADR-040 §7 lists sub-artifact sliding windows as deferred. The code already
  sub-chunked artifacts before this ADR; this decision bounds that existing
  behavior rather than introducing the deferred hybrid layer (ADR-040 Option 3).
  ADR-040's text is left unchanged; this conflict is surfaced here rather than
  silently resolved.

## Rollout (owner)

Deployment and re-ingestion are operator-owned. Pinned evaluation generations
(E1 development corpora and the held-out corpus) were built under the legacy
contract. Re-ingesting them after deployment changes their vectors and passages,
so in-flight comparisons must either finish first or be re-baselined.

## Not decided here

The rest of CI-03 (extractor behavior and immutable model digests in the reuse
identity, #313); passage-size tuning with a delivery-side evaluation; uploaded
Markdown/Docling section ingestion (#338).
