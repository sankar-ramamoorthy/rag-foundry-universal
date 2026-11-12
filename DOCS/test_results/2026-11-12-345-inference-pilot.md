---
title: "#345 pilot: num_ctx 4K/8K/16K and reviewed implementation evidence (Qwen3:4b)"
date: 2026-11-12
type: test-result
status: current
tags: [evaluation, inference, qwen3, num_ctx, ollama, issue-345, issue-342, issue-194]
related:
  - "[Issue #345](https://github.com/sankar-ramamoorthy/rag-foundry-universal/issues/345)"
  - "[Draft inference-baseline protocol](/DOCS/evaluations/2026-11-12-inference-baseline-protocol.md)"
  - "[Inference-side handoff](/DOCS/notes/20261112-inference-baseline-and-provider-capture-handoff.md)"
  - "[Raw capture index](/DOCS/test_results/raw-index.json)"
---

# #345 pilot: context allocation and implementation evidence

**Scope:** 10 seeded generations on the production Ollama host (GTX 1080 Ti,
11 GB), sent directly to Ollama with the owner's approval for bounded GPU
runs. No production configuration changed and nothing was re-ingested. This is
a pilot (n = 2 seeds per cell) that sets direction; it is not the full matrix.

## Inputs

- **Step 0 capture** (`659139bc…`, trace `592cdc63…`), taken on 2026-11-12
  from production at llm_service `82b70cd`, LiteLLM 1.109.1, Ollama 0.32.1,
  `Qwen3:4b` digest `359d7dd4…` Q4_K_M. Route `ollama/` → `/api/generate`,
  `options: {}`. The effective context was **4,096 tokens**: prompt 1,112,
  completion 1,827, `done_reason: stop`, 42.3 s total (16.4 s of it model
  load). The question asks for a trace of POST `/v1/rag` → orchestrator →
  vector retrieval. The context held 3,950 bytes of historical
  documentation and no implementation. The model said the context was
  insufficient, but it also guessed two files that do not exist
  (`rag_orchestrator/src/core/handlers/rag_handler.py`,
  `rag_orchestrator/src/retrieval/vector_retriever.py`; neither exists at the
  ingested commit `8e06335`).
- **Captured evidence arms:** the exact Step 0 prompt, with only
  `options: {num_ctx, seed}` added.
- **Implementation evidence arms:** the same system prompt and question, with
  the context replaced by
  [`implementation-context-v1.txt`](/DOCS/evaluations/inference-pilot-345/implementation-context-v1.txt):
  17,375 bytes, sha256 `eec43779…`, nine excerpts at `8e06335` in call order,
  built by `scripts/inference_pilot_345.py build-context`.
  [Answer key](/DOCS/evaluations/inference-pilot-345/impl-trace-answer-key.json).
- **Fidelity gate (passed):** rebuilding the Step 0 body from its
  `application_input.messages` reproduced the captured wire bytes and sha256
  exactly. Every arm is built by the same function, so arms differ from
  production only in `options` and, for the implementation arms, the context.
  The model digest was checked before sending.

Raw per-arm records (with request bodies, thinking and answers) are in the
gitignored `DOCS/test_results/_raw/2026-11-12-345-pilot/`. The summary is in
`_raw/2026-11-12-345-pilot-summary.json`.

## Results

| Arm | num_ctx loaded | VRAM (`/api/ps`) | done_reason | prompt | completion | prompt+completion | eval s | total s | Outcome |
|---|---|---|---|---|---|---|---|---|---|
| captured, seed 11 | 4,096 | 2.96 GiB | stop | 1,112 | 2,329 | 3,441 | 32.3 | 49.2* | admits insufficient |
| captured, seed 23 | 4,096 | 2.96 GiB | stop | 1,112 | 1,557 | 2,669 | 21.6 | 22.2 | admits insufficient |
| captured, seed 11 | 8,192 | 3.61 GiB | stop | 1,112 | 2,296 | 3,408 | 32.3 | 49.2* | admits insufficient |
| captured, seed 23 | 8,192 | 3.61 GiB | stop | 1,112 | 2,728 | 3,840 | 39.7 | 40.2 | admits insufficient |
| captured, seed 11 | 16,384 | 4.75 GiB | stop | 1,112 | 2,296 | 3,408 | 33.6 | 42.0* | admits insufficient |
| captured, seed 23 | 16,384 | 4.75 GiB | stop | 1,112 | 2,728 | 3,840 | 40.9 | 41.4 | admits insufficient |
| implementation, seed 11 | 8,192 | 3.61 GiB | stop | 3,959 | 4,261 | **8,220 > 8,192** | 69.6 | 73.7 | correct |
| implementation, seed 23 | 8,192 | 3.61 GiB | stop | 3,959 | 4,495 | **8,454 > 8,192** | 74.3 | 78.5 | correct |
| implementation, seed 11 | 16,384 | 4.75 GiB | stop | 3,959 | 4,279 | 8,238 | 71.0 | 75.2 | correct |
| implementation, seed 23 | 16,384 | 4.75 GiB | stop | 3,959 | 2,702 | 6,661 | 43.9 | 45.0 | correct, less complete |

\* includes a model (re)load of 7.6-16.1 s. Prompt evaluation took under 4 s
in every arm, so generation time dominates the latency (about 60-70 tokens
per second). Most of each completion is reasoning: 6-15k characters of
`thinking` against 1.4-3.4k characters of answer.

**Answer grading** (manual, against the reviewed sequence in the answer key):

- All four implementation answers give the right order: `rag_endpoint` →
  `run_rag` → `resolve_repo_id_http` (HTTP to ingestion) → `embed_query` →
  `hybrid_retrieve` → POST `/v1/vectors/search` (HTTP) → `similarity_search`
  endpoint → `PgVectorStore.similarity_search`. None invents a component.
  Three of four also name `_query_generation` as an HTTP call to ingestion.
- **A shared miss in all four:** none identifies the Ollama `/api/embed` HTTP
  call inside `OllamaEmbedder.embed`. One answer explicitly labels it a
  direct call. Two answers list `resolve_repo_id_http` or `hybrid_retrieve`
  as both direct and HTTP. That is defensible, since each is a direct call
  that performs HTTP, but it is imprecise.
- All six captured-evidence answers say the context is insufficient, and none
  names a file or function absent from the context or question. The unseeded
  Step 0 answer did name two nonexistent files.

## Findings

1. **The model is not the limiting factor for this question.** With reviewed
   implementation evidence, Qwen3:4b produced a correct execution trace in
   4/4 runs. With the evidence production actually retrieved, it correctly
   declined in 6/6 runs, at every context size. The Step 0 failure is an
   evidence-selection failure (#342), not a model-capability failure.
2. **For the Step 0 evidence, num_ctx made no difference.** The captured
   prompt plus reasoning (2.7-3.8k tokens) fits in 4,096. At 8K and 16K, the
   same seed produced **byte-identical output**, and every run had the same
   outcome. The current 4,096 is not truncating today's 4 KB-byte prompts.
   It does, however, perturb numerics: same-seed runs at 4K differ from those
   at 8K and 16K.
3. **The correct evidence does not fit the production context.** The
   implementation prompt alone is 3,959 tokens. At the effective 4,096,
   reasoning would have 137 tokens of room. The deployed evidence budget
   (4,096 bytes) is also about a quarter of the 17 KB this question needs.
   Supplying adequate evidence requires both a larger evidence budget (#194)
   and an explicit `num_ctx` well above 8K.
4. **8K overflows silently.** Both 8K implementation runs exceeded the window
   (8,220 and 8,454 tokens), yet Ollama reported `done_reason: "stop"`. It
   shifted the context without any signal. The seed 11 run produced reasoning
   identical to the 16K run and diverged only in the answer's last sentence,
   which is consistent with the shift happening right at the end. The answers
   stayed correct here, but **neither `done_reason` nor LiteLLM's
   `finish_reason` detects overflow**. Overflow is visible only as
   `prompt_eval_count + eval_count > context_length`.
5. **16K is cheap on this GPU.** VRAM was 2.96 GiB at 4K, 3.61 GiB at 8K and
   4.75 GiB at 16K, all fully on GPU (11 GB card). That is about 1.8 GiB more
   than 4K. The extrapolation for 32K is about 7 GiB, which is unmeasured.
   Prompt evaluation stays under 4 s, so a larger context costs little
   latency; reasoning length drives latency.

## What this does not show

- Two seeds and one question. The rates are not estimates.
- The implementation context is clean: only relevant excerpts, in call order.
  Retrieval would deliver evidence mixed with distractors and in rank order.
  How much noise the model tolerates is untested.
- The adapter comparison (`ollama/` versus `ollama_chat/`) and thinking were
  not part of this pilot.
- Whether Ollama truncates a *prompt* larger than `num_ctx` was not tested.

## Suggested next steps (each needs authorization)

1. **Implementation evidence with distractors**, at 16K: mix the reviewed
   excerpts with the Step 0 documentation chunks in production rank order, and
   at 32 KB, to see whether a realistic larger budget still yields the
   correct trace.
2. **Adapter** (`ollama/` versus `ollama_chat/`) on the implementation and
   captured sets at 16K: 2 adapters × 2 evidence sets × 2 seeds = 8
   generations.
3. **Overflow guard (no GPU needed):** llm_service could log or flag
   `prompt_eval_count + eval_count >= context_length`. This would be a
   separate issue.

Any production change, such as an explicit `num_ctx` or a larger evidence
budget, is a separate issue and PR, deployed by the operator.
