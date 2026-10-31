---
title: "E1 held-out pre-registration: predictions for named-symbol-first ordering"
date: 2026-10-31
type: evaluation-addendum
status: frozen-before-any-held-out-ingestion-or-run
tags: [held-out, adr-054, pre-registration, byte-allocation, frozen]
related:
  - "[Issue #303](https://github.com/sankar-ramamoorthy/rag-foundry-universal/issues/303)"
  - "[Stage attribution for F1-F3 (#275)](/DOCS/test_results/2026-10-31-e1-stage-attribution-f1-f3.md)"
  - "[Held-out set README (frozen)](/DOCS/evaluations/code-evidence-held-out/README.md)"
  - "[Statement-level contract](/DOCS/evaluations/code-evidence-e1/statement-level-contract.md)"
  - "[GO-rate addendum](/DOCS/evaluations/code-evidence-e1/statement-level-contract-addendum-go-rate.md)"
  - "[ADR-054: evaluation dataset isolation](/DOCS/adr/ADR-054-evaluation-dataset-isolation-and-generalization.md)"
---

# E1 held-out pre-registration: named-symbol-first ordering

Roadmap phase: Phase 6, workstream E ([roadmap](/DOCS/audit/07-Roadmap.md)). Tracked by #303,
under goal #294. Written on 2026-10-31, **before any held-out repository is ingested and before
any held-out query, control or candidate run**. It does not edit the frozen held-out manifest,
the GO rate or the statement-level contract.

## Why this exists
The mechanism below was proposed from the three development cases F1-F3, two of which fail
(#275 attribution). It was predicted on the same captures it was derived from, so that
prediction is a hypothesis, not evidence. The held-out set (12 cases, three repositories never
used for development) is the test. To keep it a test, the predictions and the refutation rules
are fixed here first.

## The mechanism under test (defined once; see the #275 note for the rationale)
When the query names an exact symbol that is present in the pre-budget candidate pool, that
symbol's chunks are placed first, before the unchanged byte allocation. Nothing else changes:
no chunking, no retrieval, no budget, no selection of other chunks. It is **not implemented**
and is not authorized by this document.

## Mechanical rules
- **Named.** A case is *named* if its query contains its `primary_function` name (the part
  after `#` in the manifest) as a whole identifier token. Applied to the frozen manifest on
  2026-10-31: **named** = H1, H2, H3, P1, P2, P3, W2, W3 (8, exactly the `explicit` style);
  **not named** = H4, P4, W1, W4 (4, exactly the `natural` style).
- **Delivered.** The primary function is *delivered* if at least one chunk labeled with its
  canonical id is in the final context. (Full evidence-gate passing is judged separately by
  the frozen contract and is not what these predictions are about.)
- **In pool.** A case's primary function is *in pool* if at least one such chunk is in the
  captured pre-budget candidate list.

## Predictions, each with its refutation
| # | Prediction | Refuted if |
| --- | --- | --- |
| P1 | In every **named** case whose primary function is in the pool, the candidate delivers it. | any such case does not deliver it |
| P2 | In every **not named** case the candidate's final context is byte-identical to the control's (the mechanism does not fire). | any not-named case differs |
| P3 | No regression: no case where the control delivers the primary function and the candidate does not. | one or more such cases |
| P4 | The candidate alone does **not** reach GO under the frozen GO rule. | the candidate reaches GO |

P4 is a deliberate prediction of insufficiency: delivering one passage of the target does not
supply the required operations and dependencies (F2/F3 counterfactual: 1/5 operations), so
statement-level delivery (#276/ADR-055) remains a separate, necessary question. If P4 is
refuted the mechanism was stronger than predicted and that is reported as a surprise, not
claimed as design success.

Not predicted and not claimed: answer correctness, any effect on `natural` cases, any effect
on repositories outside these three, any effect when the target is absent from the pool.

## Run discipline
1. **Control first, replayed twice.** The unchanged runtime runs all 12 cases twice; the final
   context hashes must reproduce. If they do not, nondeterminism is reported before any candidate
   run and the candidate comparison is limited accordingly.
2. **Candidate once.** The candidate runs once on the 12 cases, against the same corpus
   generations and the same unchanged settings (top_k 20, max_chunks_per_doc 5, 4096-byte cap,
   rerank off, the contract's model).
3. **No tuning after seeing held-out results.** Any change to the mechanism, to the rules above
   or to the case set after a held-out run requires a new dated declaration and makes the
   held-out cases *development* cases for that change; a new held-out set would then be needed.
4. **All outcomes are reported**, including refuted predictions, in a decision note
   (adopt / reject / inconclusive) under `DOCS/test_results/`.
5. **Corpus pins.** Each repository is ingested at its pinned commit (see the ingestion
   runbook); a generation whose `commit_sha` differs from the pin is not used.

## Known limits (stated before the run)
Twelve cases over three repositories; hatch's cases are concentrated on `hatch env` click
commands (manifest known limitations); the four `natural` cases test only the null prediction
P2. The result says nothing about generalization beyond this set.
