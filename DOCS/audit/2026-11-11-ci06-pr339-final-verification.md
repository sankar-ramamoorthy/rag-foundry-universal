---
title: "CI-06 final independent verification: PR #339 at 770e3c9"
date: 2026-11-11
type: audit
status: complete
summary: "Original correctness blockers resolved; recommend accepting ADR-056 and merging the reviewed commit subject to current CI; two nonblocking evidence follow-ups"
source_commit: 770e3c9088ecb9b29247ec4ec6d40f7b293df6ce
reviewer: Codex
authority: "Review evidence and recommendation; does not formally accept the ADR or authorize merge or deployment"
verification_status: "Local Ollama and PostgreSQL checks, in-memory mutation checks, capture integrity and aggregate checks, and targeted serving-model revalidation completed; current GitHub CI unverified"
tags: [audit, ci06, ci03, embedding, incremental-ingestion, issue-337, pr-339]
related:
  - "[Original independent review](/DOCS/audit/2026-11-10-ci06-pr339-independent-review.md)"
  - "[Supplied assessment of this verification](/DOCS/notes/2026-11-11-ci06-final-review-assessment.md)"
  - "[PR #339](https://github.com/sankar-ramamoorthy/rag-foundry-universal/pull/339)"
  - "[Issue #337](https://github.com/sankar-ramamoorthy/rag-foundry-universal/issues/337)"
  - "[Proposed ADR-056](/DOCS/adr/ADR-056-embedding-input-contract.md)"
  - "[Verification report](/DOCS/test_results/2026-11-10-ci06-embedding-input-coverage-verification.md)"
  - "[Frozen delivery protocol](/DOCS/evaluations/2026-11-10-ci06-delivery-evaluation-protocol.md)"
  - "[Audit index](/DOCS/audit/00-Audit-Overview.md)"
---

# CI-06 final independent verification

**Recommend accepting revised ADR-056 and merging PR #339 at `770e3c9`, subject
to normal, current CI checks.** The two original correctness blockers are
resolved. Two additional evaluation/reporting findings are nonblocking.

This is a focused follow-up to R1-R5 in the original review, not another full
architecture audit. It supersedes that review's merge recommendation for this
commit; the original report remains a valid historical assessment of `6c944dd`.
`status: complete` describes completion of this review, not shipment or formal
acceptance of the ADR.

## Resolution of R1-R5

| Finding | Independent verification | Assessment |
|---|---|---|
| R1: silent embedding truncation | All three original counterexamples passed live regression tests: strict rejection triggers splitting; stored pieces preserve the entire source and are individually accepted without truncation. Another 50 mixed-document probes checked recursive splitting, Unicode, text/vector association and ordinals across flushes. | Resolved |
| R2: generation mixing | PostgreSQL tests passed for both UPDATE branches and the three-generation failed-cleanup scenario. Removing both fences in memory made the two store tests fail: five rows moved instead of two. | Resolved |
| R3: inaccurate token-count evidence | Counter removed and measurements withdrawn; inspected provider-based verification and captures for 80,819 unique passages. Capture hashes matched. The entire 80,819-passage provider run was not repeated. | Resolved |
| R4: missing delivery evidence | Frozen protocol is byte-identical to preregistration commit `01cba02`; D1-D5 recompute from captures. | Adequate for the declared bounded evaluation, with qualifications below |
| R5: identity and rollout | Dimension added to reuse identity; model/extractor limits explicit; coordinated service deployment and clean rebuild/rollback documented. | Addressed within CI-06; broader CI-03 remains open |

The production correction handles passage overflow before persistence in
[pipeline.py:304](/ingestion_service/src/core/pipeline.py#L304). The two retag
paths constrain updates to the expected prior generation in
[pgvector_store.py:321](/vector_store_service/src/core/vectorstore/pgvector_store.py#L321)
and [line 348](/vector_store_service/src/core/vectorstore/pgvector_store.py#L348).
The revised ADR separates strict indexed passages from query truncation and
explains the relationship to ADR-040.

## Additional findings

### F1 — Medium, nonblocking: evaluation cache can bypass strict validation

Legacy requests use `truncate=True`, but their cache entries do not record that
validation provenance. Subsequently,
[strict_fit](/scripts/ci06_delivery_eval.py#L74) can reuse an entry without
checking the provider. Relevant cache handling is in
[Embeddings.ensure](/scripts/ci06_embedding_coverage.py#L437).

The reviewer reproduced this in memory: preloading a legacy-format cache entry
for `"qz" * 300` made `strict_fit` return the text unchanged without a provider
request, although the real model rejects it strictly. This defect is in the
evaluation harness; production ingestion uses the strict adapter and splitting
pipeline verified under R1.

To assess impact on the published evaluation, the reviewer identified upload
passages shared with legacy inputs but outside the independently measured
repository-path fit set:

```python
potentially_affected = (new_upload_inputs & legacy_inputs) - new_repo_inputs
```

All **4,505** such unique passages from the retained LightRAG development snapshot
were checked with `truncate=False` against the reported serving model: **zero
rejections**, 71 requests, approximately 194 seconds including extraction and
input preparation. Ollama was 0.32.1; `mxbai-embed-large:latest` digest was
`468836162de7f81e041c43663fedbbba921dcea9b9fefea135685a39b2d83dd8`.
This substantially addresses the suspected impact on these results, while the
harness defect remains.

**Open follow-up:** track strict-validation state separately and revalidate
entries obtained with truncation enabled before using them for a new-contract
evaluation. Add a regression using the cached counterexample. This report
records the follow-up locally; no separate GitHub issue was created and no
harness fix was made as part of this review. (Afterwards filed as
[#340](https://github.com/sankar-ramamoorthy/rag-foundry-universal/issues/340).)

### F2 — Low, nonblocking: statement preservation was overstated

No case's delivered **count** declined. Individual expressions can still be
lost: `R4-chain` went from one delivered expression to two, but lost
`_rank_expanded_canonical_ids` while gaining others. The old D2 result wording,
"none lost any", was therefore misleading.

The predefined D2 criterion still passes; it constrains per-case count loss,
not preservation of every individual expression. The owner subsequently asked
to record this review and the supplied assessment recommending a wording
correction. The verification report now states that no case's delivered count
declined and records the expression-level exception. No metrics or acceptance
criteria were changed.

## Evidence and practical limits

| Independent check | Result |
|---|---|
| Embedding-input and bounded-batch tests | 98 passed, including three live original counterexamples |
| Store tests, including both PostgreSQL fence paths | 17 passed |
| Incremental-ingestion integration | 8 passed, including cleanup failure and missing prior vectors |
| Query-path async offload | 4 passed |
| Additional recursive-overflow probes | 50 scenarios passed with mixed documents, varied buffer sizes and Unicode |
| In-memory fence mutation on PostgreSQL | Both store regression tests failed as expected, moving five rows instead of two |
| Raw evidence integrity | All 13 indexed CI-06 files matched recorded size and SHA-256 |
| Delivery arithmetic | D1-D5, missing-expression counts and byte bounds reproduced from captures |
| Frozen protocol | Byte-identical between `01cba02` and `770e3c9` |
| Targeted upload-cache impact check | 4,505 passages accepted strictly; zero rejections |

The passing-test total is **127**; expected mutation failures and the 50
additional scenarios are separate. Mutation was performed by replacing the
method in memory and running existing tests; source files were not edited.
The existing isolated PostgreSQL 15.15 test container was started for verification
and returned to its original stopped state. Local live tests used Ollama
0.40.15 with the same model digest as the 0.32.1 serving endpoint used for the
targeted upload check.

The [indexed captures](/DOCS/test_results/raw-index.json) remain the author's
evidence. Additional reviewer probes ran in memory; their compact observations
are recorded here, without claiming newly saved or indexed raw captures.
Neither the full provider-fit run nor the full delivery experiment was repeated.
There was no held-out evaluation, production corpus mutation or re-ingestion.
The review itself made no tracked-file changes; these documentation records
were subsequently requested by the owner.

Delivery improved **48 to 61 of 112 expected expressions** (about 27% relative,
54.5% absolute delivery). Multilingual repository hit@5 declined **102 to 94 of
150**, exactly the permitted eight-query margin; the upload path scored 114.
These are bounded evidence-survival/discovery results, not full RAG
answer-quality validation. Broader evidence delivery and the multilingual decline
remain worthwhile follow-ups. The experiment does not justify adopting
400-character passages; retain 800 for now.

Current GitHub PR/CI state could not be independently verified: `gh pr view`
returned HTTP 401. Merge should still require current green checks on the
actual merge head. Reviewer approval is tied to `770e3c9`; any subsequent runtime
changes require assessment of their delta.

## Recommendation and disposition

Accept revised ADR-056 and approve the reviewed implementation for merge subject
to current CI. Correct the reporting wording and track F1 separately, without
another architecture review cycle. The reporting correction is included in the
owner-requested documentation update accompanying this record; F1 remains open.

This recommendation does not itself change ADR-056's proposed status, merge the
PR, or authorize deployment. Deployment and clean re-ingestion remain deferred
and operator-owned. Broader CI-03 work remains separate.
