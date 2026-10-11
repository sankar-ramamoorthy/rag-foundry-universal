---
title: "Issue 254 pinned R1/R2 replay and deployed control"
date: 2026-10-11
type: test-result
status: partial-diagnostic-checkpoint
tags: [retrieval, diagnostics, issue-254, reproducibility]
related:
  - "[Issue #254](https://github.com/sankar-ramamoorthy/rag-foundry-universal/issues/254)"
  - "[Diagnostic checkpoint](/DOCS/test_results/2026-10-11-issue-254-diagnostic-checkpoint.md)"
  - "[ADR-054](/DOCS/adr/ADR-054-evaluation-dataset-isolation-and-generalization.md)"
---

# Pinned R1/R2 replay

## Result

Five saved R1/R2 requests completed through the locally instrumented HTTP
route using the real remote graph, vectors, embedding model, and LLM.
All returned HTTP 200 on the pinned generation, with Qwen3:4b. However,
their vector seeds differ from the historical requests. The local explicit
R2 request does **not** reproduce the target's chunk-count loss: `Agent.run`
never becomes a candidate.

A fresh, unchanged explicit R2 request to the deployed orchestrator **does**
reproduce the historical failure. Its seeds, expanded IDs, fetched chunk
indices, final-context manifest, and context budget equal the historical
artifact. Thus the earlier failure remains reproducible in production;
the local replay is not yet equivalent enough to attribute its individual
chunk-count limit. No retrieval correction or quality improvement is claimed.

## Provenance and procedure

- Repository: `863e770d-651e-5bc5-83d1-a1409693e707`.
- Ready generation: `24f827d7-a33b-45f7-93f4-ff6e5eaf3856`.
- Repository source: `f854303e6e44ff95d94792d24868442a28080ba2`.
- Local diagnostic code: `7522ea0`; deployed runtime:
  `f344bd58ffde5d98f4993bc0a27192b50c8decc3`.
- Requests copied verbatim from the
  [October 10 artifact](/DOCS/test_results/2026-10-10-py-coding-agent-real-repo-query-evaluation.json):
  original R1/R2, explicit overview R1/R2, explicit normal-mode R1.
  All use `top_k=10`, `rerank=false`; overview variants retain claim and
  structured controls on, canonical selection off.
- Generation readiness, ID, and source SHA verified before/after every
  request. Response generation and model checked for local requests.
- Local adapter observation records candidate order, chunk identities, and
  accepted allocation. Calling the same pure selection function without
  tracing produced identical selected chunks for all five requests.
- Local defaults and model digests are recorded; equivalence to all deployed
  process settings has **not** been verified. Generation identity alone
  does not establish runtime/configuration or vector-search parity.

Evidence: [local replay JSON](/DOCS/test_results/2026-10-11-issue-254-pinned-replay.json),
[deployed control JSON](/DOCS/test_results/2026-10-11-issue-254-deployed-control.json),
[replay harness](/scripts/issue254_pinned_replay.py).

## Separate discovery and survival findings

| Request | Local `Agent.run` discovery | Other observed losses |
| --- | --- | --- |
| Original R1 | Neither seed nor graph candidate | Exact `start_cli` and `main` passages reach final byte selection, then fail it |
| Original R2 | Neither seed nor graph candidate | Requested implementation symbols also absent; no target selection row |
| Explicit overview R1 | Neither seed nor graph candidate | Retrieved `start_cli` and `main` passages removed by overview policy |
| Explicit overview R2 | Neither seed nor graph candidate | Overview policy leaves no source passages |
| Explicit normal R1 | Neither seed nor graph candidate | Exact `start_cli` and `main` passages fail final byte selection |
| Explicit R2, deployed control | Graph rank 19, not a vector seed | Fetched indices 7, 4, 0; combined chunk-count loss before final context |

The original R2 request did not request an `Agent.run` diagnostic row; its
absence is established from the seed and expanded canonical-ID lists.
The other local requests directly trace that target. All local adapter
allocations select 50 chunks, but this does not explain the deployed loss
because their candidate sets differ.

The indexed method remains available as a canonical graph node and source
document (`1df63689-0e14-4c9f-b976-a6395e9d633b`, 15 chunks). A fenced direct
document lookup confirms availability; it is not an injected retrieval seed.

### Concrete local byte and policy exclusions

Positions below are zero-based. The byte limit remains 4096.

| Local request | Passage | Position | Bytes already consumed | Passage cost |
| --- | --- | --- | --- | --- |
| Original R1 | `start_cli`, chunk 0 | 21 | 3915 | 231 |
| Original R1 | `start_cli`, chunk 1 | 22 | 3915 | 986 |
| Original R1 | `main`, chunk 0 | 41 | 4053 | 1481 |
| Explicit normal R1 | `start_cli`, chunk 0 | 21 | 3884 | 231 |
| Explicit normal R1 | `start_cli`, chunk 1 | 22 | 3884 | 986 |
| Explicit normal R1 | `main`, chunk 0 | 44 | 4089 | 1481 |

In explicit overview R1 these passages instead survive chunk selection and
are excluded at `overview_policy` (positions 21, 22, 44). The detailed new
trace distinguishes this from the legacy `dropped_by_reranker` label, which
can describe the post-policy result even when `rerank=false`. No legacy
diagnostic behavior was changed in this replay.

## Answers and citations are separate observations

- Original local R1 returns an empty answer despite HTTP 200 and source entries.
- Original local R2 answers from specifications and historical documentation;
  it does not establish the requested implementation flow.
- Both local overview variants have empty final source manifests/citations.
  Their generated responses overstate the inventory evidence as excluding
  `py_mono`; missing retrieved passages do not establish absent indexed code.
- Explicit normal R1 describes a flow using ADR/CLI evidence, but does not
  cite the exact `Agent.run` method. Answer plausibility is not source survival.

These are diagnostic observations, not a newly scored frozen benchmark.
They are development data under ADR-054, not held-out generalization results.

## Remaining attribution gap and next bounded step

**Verified:** the deployed explicit R2 reproduces discovery, fetch, and
combined chunk-count loss. **Not verified:** which individual deployed
limit first rejects these three target chunks. The global 50-chunk cap
remains a supported inference, not a confirmed attribution for this run.

Before another instrumented full replay, establish local/deployed parity of
effective embedding and seed-search configuration and inputs, then compare
seed outputs. No evidence here identifies a particular configuration,
embedding, ANN behavior, or instrumentation change as the cause of the
mismatch. Do not tune retrieval parameters to obtain the desired seeds.
Once equivalent inputs are established, replay explicit R2 with the new
first-exclusion trace and record the competing accepted allocation.

The harness passes Ruff and Pyright. Production code/tests are unchanged
from the diagnostic checkpoint (386 tests passed there). No deployment,
re-ingestion, ranking/budget/prompt change, PR, merge, or issue closure.
