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
   complete text the embedding model encoded. No stored passage is ever
   embedded from a shortened input, by the client or the server.
2. **One contract module.** `shared/embedders/input_contract.py` owns the
   packing budgets (800 characters; 480 by `estimate_tokens`) and the contract
   identifier (`exact-input-v3`). The token estimate is a packing heuristic,
   not an upper bound on real tokens.
3. **The model is the final guard.** Every passage request sets
   `truncate: false`. If the model rejects a passage as longer than its context,
   the ingestion pipeline splits it into exact consecutive pieces (verbatim
   slices that together cover it), embeds each in full, and keeps the
   artifact's ordinals consecutive, across embedding-buffer flushes too. A
   passage that cannot be split further fails the ingestion. Rejected batches
   are bisected to find the offending inputs.
4. **Repository artifacts** are chunked into exact line windows: in-order
   slices covering the whole artifact, ending on line boundaries, repeating up
   to 100 characters of whole lines between windows.
5. **Document uploads** keep their existing strategy selection with every unit
   fitted to the budgets. Rule 3 applies to them as well.
6. **Queries** are not stored evidence. An over-context query is embedded as a
   server-truncated prefix and a warning is logged; it never fails the request.
7. **Reuse identity.** Chunking version `budgeted-v2`; embedding version
   `<provider>:<model>:<dimension>d:exact-input-v3` (provider, model and
   dimension per FR-006 of the
   [incremental lineage spec](/specs/006-incremental-ingestion-lineage/spec.md),
   plus this contract). A generation built under any other string is fully
   re-embedded once. Any change to a budget or to input handling bumps the
   contract.
8. **Generation-fenced reuse.** Reused vectors are retagged only from the
   expected prior generation, never by `document_id` alone, and the vector
   store reports which documents it moved. A reusable artifact without vectors
   in that generation is embedded instead. Cleanup of superseded generations
   stays best-effort and is not relied on for correctness.

## What the reuse identity does and does not establish

It establishes that the prior generation used the same chunking version,
provider, model name, dimension and input contract. It does **not** identify
the model's immutable digest (a mutable tag such as `:latest` can change
weights), effective inference configuration, or extractor behavior. Those are
the remaining CI-03 work (#313). Until then, operators must pin the served model
during a migration and use `force_full_rebuild` after changing the model behind
a tag.

## Relationship to ADR-040

ADR-040 describes one embedding unit per artifact and defers sub-artifact
windows. The implementation already sub-chunked artifacts before this ADR. This
decision governs passage sizing only: an artifact maps to one or more exact,
model-sized passages, while artifacts remain the graph, identity and retrieval
unit. ADR-040's hybrid chunk layer (retrieval units independent of artifacts)
remains deferred. ADR-040 carries a note pointing here.

## Alternatives considered

Measured in the [verification](/DOCS/test_results/2026-11-10-ci06-embedding-input-coverage-verification.md):

| Option | Outcome |
| --- | --- |
| Remove embedder truncation only | Full character coverage, but many inputs exceed the context, which Ollama would truncate silently by default. Rejected. |
| Larger character budget (1,000–1,500) | More inputs exceed the context. Rejected. |
| Truncate as a recorded last resort (first version of this ADR) | Contradicts the invariant; the review reproduced budget-compliant passages that were stored whole but embedded truncated. Replaced by rule 3. |
| Fail ingestion on any overflow | Correct but brittle: one unusual line would block a whole repository. Kept only for passages that cannot be split further. |
| Exact tokenizer in the chunker | No tokenizer endpoint in the serving Ollama, and an offline WordPiece reimplementation diverged from it. The model's own rejection is exact; the estimate only reduces how often splitting is needed. |
| Fit legacy heuristic units (rule 5 applied to code) | Fixes coverage, but controls ranked consistently worse and it needs about 17% more code passages. Used only for document uploads. |
| Line windows at 400–500 characters | Best needle discovery at 400, but about 1.8× the vectors and half the evidence per passage under count-based caps. Deferred. |

## Consequences

- Coverage of artifact text in embedding inputs goes from about 88–90% to
  complete on the measured development corpora, and every stored passage is
  verified to fit by the serving model at ingestion time.
- Fewer passages than legacy in aggregate (−22.5% and −4.9% on the two
  corpora); individual artifacts can get more (a 128,000-character single line
  goes from 143 to 160 passages), and overflow splitting adds pieces.
- Discovery and delivery effects: see the
  [verification](/DOCS/test_results/2026-11-10-ci06-embedding-input-coverage-verification.md)
  and the pre-registered [delivery evaluation](/DOCS/evaluations/2026-11-10-ci06-delivery-evaluation-protocol.md).
- Repository passages are verbatim, preserving whitespace the old
  sentence/paragraph strategies normalized.
- Queries over 800 characters change behavior as soon as the shared embedder is
  deployed, before any re-ingestion (rule 6).

## Rollout and rollback (owner)

Deployment and re-ingestion are operator-owned.

- **Deploy together.** `vector_store_service` and `ingestion_service` must ship
  together: the retag request now requires the expected generation, and the
  ingestion client refuses a response without the moved document IDs.
- **Migration inventory.** Every repository's next ingestion re-embeds all of
  its artifacts once; budget the time from that repository's last full
  ingestion. Uploaded documents have no reuse gate and keep their legacy
  passages until re-uploaded.
- **Pin the model** for the migration and record its digest with the run.
- **Pinned evaluation generations** (E1 development and held-out corpora) were
  built under the legacy contract; re-ingesting them changes their passages and
  vectors. Finish or re-baseline in-flight comparisons first.
- **Rollback** is not free: older code writes the legacy identity strings, so
  the next ingestion after a rollback re-embeds everything again. Restoring the
  old index means re-ingesting under the old code.

## Not decided here

The rest of CI-03 (#313); passage-size tuning beyond the bounded evaluation;
uploaded Markdown/Docling section ingestion, which fails on `main` for an
unrelated reason (#338).
