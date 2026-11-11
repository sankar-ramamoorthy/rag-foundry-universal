---
title: "CI-06 investigation: embedding-input coverage"
date: 2026-11-10
type: investigation
status: complete
source_commit: 75c3b4c68b5aa784eb2ac62723ad0583901b91a0
scope: "Chunking, embedding input preparation and the incremental-reuse gate for repository and document ingestion"
authority: "Investigation record for #337; the decision is proposed in ADR-056 and implemented on fix/337-ci06-embedding-input-coverage for owner review"
verification_status: "Measured on two development corpora with the real extractor, chunker and model; sampled discovery evaluation; unit and real-PostgreSQL tests. No deployed-stack or held-out measurement."
tags: [audit, investigation, code-intelligence, embedding, chunking, ci06, ci03]
related:
  - "[November 10 architecture audit](/DOCS/audit/2026-11-10-code-intelligence-architecture-audit.md)"
  - "[Independent review and response](/DOCS/audit/2026-11-10-code-intelligence-independent-review-and-response.md)"
  - "[ADR-056 (proposed)](/DOCS/adr/ADR-056-embedding-input-contract.md)"
  - "[Verification and measurements](/DOCS/test_results/2026-11-10-ci06-embedding-input-coverage-verification.md)"
  - "[Implementation plan](/specs/005-production-correctness/ci06-plan.md)"
  - "[Issue #337](https://github.com/sankar-ramamoorthy/rag-foundry-universal/issues/337)"
---

# CI-06: Embedding-input coverage

> [!abstract] Outcome
> The finding is confirmed and larger than the audit's illustration: about
> 10–12% of non-whitespace artifact text reached no embedding input. A shared
> embedding-input contract now makes every stored passage the exact model input,
> sized to the model's real limit, with the model's own rejection as the final
> guard. Discovery of previously omitted text roughly doubles on sampled
> queries; effects on already-covered text are small and mixed; a pre-registered
> bounded delivery evaluation passed. Revised 2026-11-11 after the
> [independent review](/DOCS/audit/2026-11-10-ci06-pr339-independent-review.md)
> (§9).

## 1. Question and invariant

The [audit](/DOCS/audit/2026-11-10-code-intelligence-architecture-audit.md)
asked whether indexed source is represented in the vectors used for discovery.
The [review response](/DOCS/audit/2026-11-10-code-intelligence-independent-review-and-response.md)
asked for three separate outcomes: input coverage, discovery quality and
delivery quality, plus reuse/invalidation behavior before any re-embedding.

Invariant adopted: **a stored passage is the exact, complete text the embedding
model encodes.** Coverage then follows from chunking alone. Chunking must cover
the artifact, and each passage must fit one model input.

## 2. Current behavior (at `75c3b4c`)

- Repository artifacts and uploaded text were chunked by a length heuristic in
  `shared/chunkers/selector.py`. Below 2,000 characters it used sentence units;
  below 10,000, paragraph units; otherwise 1,000-character windows with
  100-character overlap. Sentence and paragraph units had no upper bound.
- `shared/embedders/ollama.py` cut every input to 800 characters, then 400
  words, without telling the caller.
- Ollama's `/api/embed` silently truncates to the model context (512 tokens for
  `mxbai-embed-large`) unless the request sets `truncate: false`, in which case it
  returns an error. This was confirmed against the running model.
- The stored passage (`chunk_text`) was the untruncated chunk. Delivery could
  therefore show text that never influenced the vector.
- Reuse eligibility compared `ChunkerFactory.VERSION` and
  `<provider>:<model>`. Neither described the embedder's truncation.

## 3. Counterexample and measurement

The audit's marker probe is now a unit test: a marker at characters 800–900 of a
large artifact. The legacy contract dropped it; the new contract embeds it.

Corpus-level measurement (details in the
[verification](/DOCS/test_results/2026-11-10-ci06-embedding-input-coverage-verification.md)):

- 11.5% of code text and 10.0% of documentation text in this repository, and
  10.2% and 12.2% in LightRAG, reached no input. 1,491 and 4,624 artifacts were
  partially unrepresented.
- The dominant cause was oversized sentence/paragraph units, not the window gap.
- A second, independent loss: Ollama silently truncates inputs past 512 tokens
  by default. The first estimate of how many legacy inputs this hit (376) came
  from an offline counter later shown to be inexact and is withdrawn (§9).

## 4. Alternatives

Pairs of figures are foundry / LightRAG.

| Option | Coverage | Token fit | Passages vs legacy | Notes |
| --- | --- | --- | --- | --- |
| A. Remove the client cut only | complete | many overflows (offline estimate, withdrawn) | same | Moves the silent loss to the server. |
| B. Larger character budget (1,000–1,500) | complete | overflows grow quickly | fewer | 18% of sampled code windows at 1,500 characters hit the limit. |
| C. Fit legacy units to 800 characters + token estimate | complete | model guard | +13% / +18% | Controls consistently slightly worse. |
| D. Exact line windows, 800 characters + token estimate | complete | model guard; 0 rejections on the serving model | −22.5% / −4.9% | Chosen for repository artifacts. |
| E. Line windows, 400–500 characters | complete | model guard | +82% (400) and +43% (500) in the foundry sample | 400 best on needle discovery; delivery not evaluated. |
| F. Model tokenizer inside the chunker | complete | exact | n/a | No tokenizer endpoint in the serving Ollama; an offline reimplementation diverged from it. |

The token estimate (`estimate_tokens`) counts each punctuation or non-ASCII
character as one token and an ASCII alphanumeric run of length L as ⌈L/3⌉. It
is a packing heuristic, not a bound: rare letter runs can need far more real
tokens. The serving model's strict rejection is the guard (ADR-056 rule 3).

## 5. Discovery and delivery

Needle queries targeting text the legacy contract omitted improved strongly under
C, D and E (p < 0.001). For already-covered text, D was slightly better on one
corpus by hit@5 and slightly worse on the other. E (400) was neutral or better
but its advantage partly reflects the needle metric, which favors small passages.

The orchestrator selects a fixed **number** of passages per artifact, so passage
size directly sets delivered evidence per artifact; that is why 800 was kept
rather than 400. A bounded, pre-registered delivery evaluation of 800 against
legacy passed all five criteria (verification). 400 was not evaluated for
delivery.

## 6. Relationship with CI-03

- **Transformation identity.** The contract has its own identifier
  (`exact-input-v3`), included with provider, model and dimension in the
  embedding version string. Both strings are recorded per generation with no
  schema change.
- **Incremental reuse.** The all-or-nothing gate re-embeds every artifact when
  either string differs. Reuse itself is now fenced to the expected prior
  generation (ADR-056 rule 8), because stale rows left by a failed cleanup could
  otherwise be relabeled into a new generation even with one contract
  throughout. Verified against PostgreSQL.
- **Migration.** Owner decision: existing indexes are rebuilt cleanly at
  deployment; no historical compatibility is kept.
- **Not solved here.** Extractor behavior and the immutable model digest are
  still absent from the reuse identity (#313). An input-text fingerprint per
  vector would allow selective reuse across contract changes; that is a CI-03
  design question, not needed for this all-or-nothing transition.

## 7. Related defects found

Uploaded Markdown and Docling section ingestion (`run_with_sections`) fails on
`main` since the IR refactor because it iterates an `ExtractionResult`. Filed as
#338; the section path should adopt this contract when it is repaired.

## 8. Decision

Adopt option D for repository artifacts and option C's per-unit fit for document
uploads, under the contract in
[ADR-056](/DOCS/adr/ADR-056-embedding-input-contract.md) (proposed). Owner
decisions remaining: ADR acceptance and rebuild timing relative to pinned
evaluation corpora.

## 9. Revision after the independent review (2026-11-11)

The [review](/DOCS/audit/2026-11-10-ci06-pr339-independent-review.md) found that
budget-compliant passages could still be stored beside a truncated embedding
(R1), that reuse could relabel stale rows from a failed cleanup (R2), that the
offline token counter was not the serving tokenizer (R3), and that delivery was
unmeasured (R4). All four were independently reproduced or accepted and are
resolved as recorded in the
[verification](/DOCS/test_results/2026-11-10-ci06-embedding-input-coverage-verification.md#review-follow-up-r1r5).
Token-fit figures from the offline counter are withdrawn.
