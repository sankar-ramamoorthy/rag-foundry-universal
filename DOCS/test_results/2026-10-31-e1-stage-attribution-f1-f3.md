---
title: "E1 stage attribution for F1-F3: where the target is lost between discovery and the final context"
date: 2026-10-31
type: evaluation-report
status: diagnosis-complete-f1-f3-only-no-implementation
tags: [evidence-coverage, stage-attribution, byte-allocation, diagnosis]
related:
  - "[Issue #275: target-first selection](https://github.com/sankar-ramamoorthy/rag-foundry-universal/issues/275)"
  - "[Issue #300: pre-budget pool capture](https://github.com/sankar-ramamoorthy/rag-foundry-universal/issues/300)"
  - "[Control replay on the clean corpus (#297)](/DOCS/test_results/2026-10-31-e1-clean-corpus-control-f1-f3.md)"
  - "[E1 baseline results](/DOCS/test_results/2026-10-14-code-evidence-e1-results.md)"
  - "[Statement-level delivery contract (#276)](/DOCS/evaluations/code-evidence-e1/statement-level-contract.md)"
---

# E1 stage attribution for F1-F3

Diagnosis only. Method: `scripts/e1_stage_attribution.py` reads the pool-capturing control
captures (`control-pool-F1..F3`, #300; byte-identical final contexts to the baseline and the
earlier control) and reports, per case, the first stage at which the target symbol is lost.
The runtime's own `evidence_trace` (`found_by_vector`, `chunk_fetched`,
`survives_chunk_limits`, `reaches_final_context`, `drop_reason`) agrees with the
pool-derived stages in every case. Raw captures are git-ignored and hashed in `raw-index.json`.

## Attribution table
| Case | Discovered | Document cap | Fetched | In pre-budget pool | In final context | First stage lost |
| --- | --- | --- | --- | --- | --- | --- |
| F1 `assemble_context` | yes (seed rank 11) | yes | yes | yes, pool positions 0-2 (754 B) | **yes** | none |
| F2 `get_cached_graph_with_generation` | yes (seed rank 10) | yes | yes | yes, positions 12-14 (1,242 B) | **no** | **byte allocation** (`dropped_by_token_budget`) |
| F3 `run_rag` | yes (seed rank 14) | yes | yes | yes, positions 36-38 (3,000 B) | **no** | **byte allocation** (`dropped_by_token_budget`) |

The pool has 50 chunks per case; the budget is 4,096 bytes; the assembler is first-fit in pool
order and skips any passage that does not fit.

## Why the byte stage loses it
- **F2:** four documents precede the target in the pool (a caller in `evidence_service.py`, three
  ADR / test-result documents; 9 documentation + 3 source chunks). They consume the budget
  (final slack 46 B); the target's smallest chunk is 264 B.
- **F3:** thirteen documents precede the target (33 documentation chunks, 3 source). The final
  context is nine chunks of archived handover / cheat-sheet text; slack 133 B; each target
  chunk is 1,000 B.
- All three queries **name the symbol and its file path explicitly.** The target is asked for by
  name, found, fetched, and still not delivered.
- F1 is delivered; its remaining miss (the UTF-8 counting helper, 3/4 operations) is a
  dependency/granularity question and belongs to #276, not to this issue.

## Predicted effect of one mechanism (offline counterfactual, not a run)
Mechanism for the only failing stage: when the query names an exact symbol that is in the
pool, place that symbol's chunks first before the unchanged byte allocation. Replaying the
runtime's own `assemble_context` on the captured pools with the target's chunks moved to the
front gives:

| Case | Target chunks in final: now -> predicted | Operations | Dependencies |
| --- | --- | --- | --- |
| F1 | 3 -> 3 | 3/4 -> 3/4 | 3/3 -> 3/3 |
| F2 | 0 -> 3 | 0/5 -> 1/5 | 0/3 -> 2/3 |
| F3 | 0 -> 3 | 0/5 -> 1/5 | 0/3 -> 0/3 |

**Falsifiable claims:** (1) target in the final context 3/3 on F1-F3 with no regression on F1;
(2) the claim is **refuted** if any case still misses the target, or F1 loses it. **What it does
not claim:** it does not pass the evidence gate (most operations are still missing, because only
three whole passages of the target are delivered under the per-document cap of five chunks), so
statement-level delivery (#276) remains a separate, necessary question. The counterfactual
assumes the pool and its other chunks are unchanged and ignores displacement effects on other
evidence; only a real run can test it.

No other stage needs a mechanism for these cases: discovery, document cap, fetch and chunk
limits all passed.

## Limits
- **F1-F3 only.** L1-L3 have no completed control (#270 open), so the LightRAG cases are not
  attributed; the baseline's L2 loss at the document cap is not reproduced here.
- Three cases on one repository say nothing about generalization (ADR-054); the frozen held-out
  set (12 cases, three repositories) is the test, and no held-out repository is ingested yet.
- The counterfactual is a prediction. No retrieval-policy change is authorized or implemented.
