---
title: "#345 inference-baseline protocol: context size, provider adapter, thinking (DRAFT)"
date: 2026-11-12
type: evaluation
status: draft
tags: [evaluation, inference, qwen3, num_ctx, ollama, litellm, issue-345]
related:
  - "[Issue #345](https://github.com/sankar-ramamoorthy/rag-foundry-universal/issues/345)"
  - "[Issue #194](https://github.com/sankar-ramamoorthy/rag-foundry-universal/issues/194)"
  - "[Inference-side handoff](/DOCS/notes/20261112-inference-baseline-and-provider-capture-handoff.md)"
  - "[Deployment and Step 0 runbook](/DOCS/deployment/2026-11-12-capture-deploy-and-step0-runbook.md)"
  - "[E1 manifest](/DOCS/evaluations/code-evidence-e1/README.md)"
---

# #345 inference-baseline protocol (DRAFT, not frozen, not authorized)

**Status:** a draft for owner review. It is frozen only after Step 0's record
is in hand, because several parameters (the default `num_ctx` arm, the GPU
budget, the use of 32k) depend on it. **No GPU arm runs until the owner
explicitly authorizes it**, phase by phase.

## Question

Does Qwen3:4b, as production calls it, operate under unintended inference
constraints, independently of retrieval? This protocol tests the effective
context allocation, the prompt representation (flattened `ollama/` versus
role-preserving chat), and then whether more evidence helps once the model
can hold it.

## Constraints

- **Production defaults never change** during #345. Arms vary settings only in
  provider requests sent directly to Ollama. Any recommended change becomes a
  separate issue and PR, deployed by the operator.
- **One factor at a time**, with evidence frozen to exact bytes.
- **Use the wire `done_reason`, not LiteLLM's `finish_reason`.** In a
  stub-based check on 2026-11-12, Ollama's `done_reason: "length"` came back
  through LiteLLM's `ollama/` route as `finish_reason: "stop"`: LiteLLM can
  report a truncated generation as complete. This was verified against a stub,
  not yet against real Ollama.

## Inputs

**Set A: fixed 4 KB contexts (exists, no GPU needed to build).** These are the
exact `{context, query}` pairs that E1 sent to `/generate` (local raw captures
`code-evidence-e1/baseline-*.json`, indexed in `raw-index.json`):

| Case | Context bytes | Context sha256 (prefix) |
|---|---|---|
| L1 | 3,960 | `945c8203bf12` |
| L2 | 3,940 | `e957d3301c01` |
| L3 | 4,065 | `61854ff7a78e` |
| F1 | 4,038 | `e4efa87571eb` |
| F2 | 4,050 | `43024ce8a5a1` |
| F3 | 3,963 | `e98b6a251d27` |

**Set B: larger evidence budgets (built without GPU).** This set covers the six
E1 cases plus the two #342 LightRAG questions, at `max_total_tokens` ∈ {16384,
32768} bytes. The contexts are assembled by an unchanged *local* orchestrator
against the deployed read-only services, the same way the E1 harness works
([agent execution boundaries](/DOCS/deployment/agent-execution-and-verification.md)).
`/generate` is stubbed out, so building Set B uses no GPU; only the query
embedding runs. Each repository generation is checked to be `ready` and
unchanged before and after assembly.

## Request construction and the fidelity gate

Every arm's body is built from `{context, query}` with `rag_answer.v1`'s
`build_messages()`:

- **`generate` (flattened):** the `/api/generate` body exactly as LiteLLM's
  `ollama/` route builds it (the `### System:` / `### User:` prompt string).
- **`chat` (roles):** the `/api/chat` body exactly as LiteLLM's `ollama_chat/`
  route builds it (a system and a user message).

**Gate:** the runner must first rebuild the Step 0 capture's body from that
record's `application_input.messages` and match its captured wire bytes
exactly. It must also match LiteLLM's `ollama_chat/` body produced against a
stub. If either check fails, nothing runs.

**Cache control (added after round 2):** same-seed requests gave
different outputs depending on whether the prompt prefix was cached
([round 2](/DOCS/test_results/2026-11-12-345-round2.md), finding 4). Before
the protocol is frozen, decide how each arm starts. One option is
unload-between-arms (`keep_alive: 0`). Record the cache state per arm
(`prompt_eval_duration` near 0 indicates a hit).

## Fixed settings in every arm

These are sent explicitly, so "explicit versus default" cannot confound the
comparison:

- The model digest is pinned to Step 0's digest. A digest change aborts the
  run.
- `temperature`, `top_k`, `top_p` and `repeat_penalty` are set to the
  Modelfile values recorded in Step 0.
- `seed` takes the values {11, 23}: two seeded runs per cell.
- `num_predict` is the same in every arm, with the value fixed when the
  protocol is frozen; `done_reason: "length"` is recorded when it is hit.
- `think` is left unset (current behavior) in Phases A and B.

## Phases

Each phase needs separate authorization.

**Phase A: context allocation × adapter, on Set A.**
- `num_ctx` ∈ {the effective default from Step 0, 16384}.
- Adapter ∈ {generate, chat}.
- 6 cases × 2 seeds = **48 generations**.
- If Step 0 shows the default is already ≥ 16384, the `num_ctx` factor drops
  and Phase A becomes 24 generations.

**Phase B: evidence budget, on Set B.**
- Uses Phase A's better adapter (current if they tie) and a `num_ctx` large
  enough for the largest prompt plus the observed reasoning output. That means
  32768 if Step 0's VRAM headroom allows it (the arithmetic estimate is about
  6.8 GiB), otherwise 16384 with Set B capped to fit.
- Budgets {4096, 16384, 32768} bytes × 8 cases × 2 seeds = **48 generations**.
  The results feed #194.

**Phase C (optional): thinking.** Unset versus `think: false`, on the Phase B
winner. It is sized and authorized separately.

**GPU estimate:** about 96 generations for Phases A and B. The wall-clock
estimate is filled in from Step 0's `eval_duration` before authorization is
requested. The runner has a `--dry-run` that sends nothing, and a
`--phase A|B|C` flag that refuses to run without `--authorized`.

## Measurements (per generation)

- **Truncation:**
  - wire `done_reason`
  - `prompt_eval_count` compared with the prompt's own token estimate (a
    shortfall means Ollama truncated the prompt)
  - `eval_count`
- **Cost:** `prompt_eval_duration`, `eval_duration`, `total_duration`, and
  `/api/ps` `size_vram` after the call.
- **Answer key hits:**
  - Among the case's key identifiers that are present in that arm's context,
    how many the answer names.
  - **Named without evidence:** key identifiers absent from the context but
    named in the answer. This is not necessarily fabrication: LightRAG may be in
    the model's training data. It is reported, not scored as an error.
  - **Admission:** when no key identifier is present, whether the answer says
    the context is insufficient. The regex list is frozen with the protocol.
- Every request and response is stored as an `llm_provider_capture`-style
  record, indexed in `raw-index.json`.

### Answer keys (draft)

Each key is the set of called identifiers in the case's manifest operation and
dependency expressions, with generic builtins excluded. "Present at 4 KB"
refers to Set A.

| Case | Key identifiers | Present at 4 KB |
|---|---|---|
| L1 | `_apply_token_truncation`, `atruncate_list_by_token_size`, `acount_tokens` | none |
| L2 | `_apply_token_truncation`, `atruncate_list_by_token_size`, `acount_tokens` | none |
| L3 | `atruncate_list_by_token_size` | all |
| F1 | `_render_chunk`, `conservative_token_count`, `AssembledContext` | all |
| F2 | `get_repo_generation`, `CodebaseGraph`, `load_graph_for_repo`, `popitem`, `move_to_end` | `load_graph_for_repo` |
| F3 | `conservative_token_count`, `assemble_context`, `build_final_context_manifest` | none |

`popitem` and `move_to_end` (F2) are generic dict methods; whether they stay in
the key is decided at freeze time.

So at the current 4 KB budget, three of six cases cannot be answered from the
evidence. Set A therefore tests truncation, the adapter and honesty; Set B
tests whether more evidence helps. The #342 questions' keys are added at
freeze time.

## Decision rules (draft; these produce recommendations only)

- **Adapter:** recommend `ollama_chat/` if, on Set A, chat has at least as
  many key hits as generate in every case and seed pair and strictly more in
  total, or equal hits with fewer identifiers named without evidence. Otherwise, no change.
- **`num_ctx`:** recommend an explicit `num_ctx` of N if the default arm shows
  prompt truncation or `done_reason: "length"` where N shows none, with
  `size_vram` under 80% of total GPU memory.
- **Evidence budget:** Phase B's survival and key-hit curve goes to #194,
  which decides the orchestrator budget.

## Not in scope

Retrieval ranking and expansion, model replacement (including `qwen3.5:4b`),
and any production default change.
