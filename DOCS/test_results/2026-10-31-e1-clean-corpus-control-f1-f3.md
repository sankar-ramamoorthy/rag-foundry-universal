---
title: "E1 control replay of F1-F3 on the clean development corpus"
date: 2026-10-31
type: evaluation-report
status: control-complete-no-candidate-evaluated
tags: [evidence-coverage, control, development-corpus, equivalence]
related:
  - "[Issue #297: matched control on the clean corpus](https://github.com/sankar-ramamoorthy/rag-foundry-universal/issues/297)"
  - "[Issue #292: clean development corpus](https://github.com/sankar-ramamoorthy/rag-foundry-universal/issues/292)"
  - "[Dev corpus pin](/DOCS/evaluations/code-evidence-e1/dev-corpus-pin.json)"
  - "[E1 baseline results](/DOCS/test_results/2026-10-14-code-evidence-e1-results.md)"
  - "[Raw capture index](/DOCS/test_results/raw-index.json)"
---

# E1 control replay of F1-F3 on the clean development corpus

## What was run
`scripts/code_evidence_experiment.py control` (PR #298), 2026-10-31: the unchanged local
orchestrator code with the remote services (deployed `88fa1b7`), F1-F3 only, `top_k` 20,
`max_chunks_per_doc` 5, 4096-byte cap, rerank off, Qwen3:4b, against repo
`a6e336ef-d0ee-54dd-a687-140dc1df17d3`, ingestion `d1dfbf70-7a95-4b0e-b3ed-786b9e68b4f9`,
commit `109f12d8`. Sequential, one graph load per case, no retries; all three completed with
no timeout or error. The generation was asserted `ready` and unchanged around each case.
Raw captures are git-ignored (`_raw/code-evidence-e1/control-F*.json`), hashed in
`raw-index.json`.

## Result
| Case | Target discovered / survived | Operations | Dependencies | Delivered bytes | Context SHA-256 vs 2026-10-14 baseline |
| --- | --- | --- | --- | --- | --- |
| F1 | yes / yes | 3/4 | 3/3 | 4038 | **identical** (`e4efa875...`) |
| F2 | yes / yes | 0/5 | 0/3 | 4050 | **identical** (`43024ce8...`) |
| F3 | yes / yes | 0/5 | 0/3 | 3963 | **identical** (`e98b6a25...`) |

Seed and expanded canonical ids also equal the baseline's in all three cases. The generated
answers differ (the model is not deterministic); the delivered contexts, which are what the
experiment scores, do not.

## What this shows, and what it does not
- **Corpus equivalence, much stronger than before:** the clean corpus reproduces the lost
  generation's final contexts byte for byte for F1-F3. That is observational evidence that
  retrieval over the clean corpus behaves as it did over the original; it still does not prove
  the original and clean rows are identical (the original rows are gone).
- **A valid matched control for F1-F3 now exists.** Candidate comparisons on F1-F3 can use
  these captures. The 2026-10-14 baseline and this control agree, so either serves as the
  reference for these cases.
- **Not shown:** nothing about L1-L3 (LightRAG, #270 still open), no candidate mechanism, no
  held-out result, no claim about generalization (ADR-054).
- **Pre-budget candidate pool: not recorded.** The existing observers do not expose it, so
  #275's prerequisite (the pool per case) is still missing. Recording it needs a harness
  change that must not alter selection.
- The control completed against the clean corpus's 9 MB graph without incident; this says
  nothing about why the 37 MB LightRAG request preceded an engine stop.
