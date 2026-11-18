---
title: "Ordinary RAG evidence budgets and Ollama capacity profiles"
date: 2026-11-18
type: note
status: complete
related:
  - "[Phase 6 issue #386](https://github.com/sankar-ramamoorthy/rag-foundry-universal/issues/386)"
  - "[Automatic Custom admission #394](https://github.com/sankar-ramamoorthy/rag-foundry-universal/issues/394)"
  - "[Provider request capture](/DOCS/deployment/llm-provider-request-capture.md)"
---

# Configure an evidence budget

Use matching orchestrator and LLM service versions. The ordinary RAG API accepts
`context_mode` values `auto`, `compact` and `custom`. Custom requires a positive
integer `max_evidence_bytes`. Set `COMPACT_EVIDENCE_BYTES` (default 2048) and
`MAX_EVIDENCE_BYTES` (default 32768) at the orchestrator. Auto requests
4,096 bytes. The orchestrator applies its configured prompt and output reserves
to Auto, Compact and repository overview queries.

For an ordinary repository question, Custom first selects whole passages up to
the requested amount and deployment ceiling. The LLM service checks the
complete prompt for each candidate, reserves output, and can drop trailing
passages to fit its window. The orchestrator verifies the serving candidate's
passage count and SHA-256 before returning the answer and citations. Missing
or inconsistent delivery metadata fails the request. Deploy the orchestrator
and LLM service together.

`retrieval_plan.evidence_budget` records requested, effective and delivered
bytes, the binding limit, and passages skipped at final byte assembly. The
per-passage rendered size includes its source label. Joining separators are
reported separately. Earlier ranking and chunk-count exclusions remain in the
retrieval trace. The evidence manifest describes selected passages. Overview
policy text can add instructions and evidence after that stage, and the LLM
service counts the entire rendered prompt for admission. A deterministic
structured overview can return directly without invoking a provider.

## Automatic Ollama admission for Custom

Select Qwen3:4b in Gradio and enter the desired evidence bytes. A cold model
loads with the backend's default window. If a runner is already loaded, the
LLM service reads its current allocation from `/api/ps`. A small allocation
can reduce the delivered evidence. Setting Custom does not resize the GPU
allocation. The service verifies the runner again after generation.

This release verifies Ollama 0.32.1's render-only generation behavior. The
service uses the model's rendered prompt, a conservative token bound and
the configured output reserve. The final call disables input truncation and
context shifting. Each fallback undergoes the same checks. Unsupported
servers and tokenizers can produce a capacity error. Auto remains available
on those deployments.

## Administrative capacity profiles

The LLM service reads optional top-level `rag_capacity_profiles` from its
models YAML. Each profile requires the exact LiteLLM `model` (initially
`ollama/<name:tag>`), resolved `api_base`, full lowercase 64-hex `digest`,
`window_tokens` and `template_overhead_tokens`. Profiles are operator
attestations for a fixed model, backend and template. Calibrate against actual
runner observations before enabling one. Confirm that the tokenizer's input
token count is bounded by rendered UTF-8 bytes plus the specified overhead
for all supported inputs. Include BOS, server-side system text and model
template expansion in the bound. Leave models with unverified or unbounded
template expansion unprofiled. Revalidate on backend/template changes.

```yaml
rag_capacity_profiles:
  - model: ollama/<installed-name:tag>
    api_base: ${REMOTE_OLLAMA_BASE_URL}
    digest: "<full digest from the verified runner>"
    window_tokens: <verified usable window>
    template_overhead_tokens: <verified upper bound>
```

Before dispatch, the service checks the digest on the configured endpoint and
uses LiteLLM's Ollama transform to measure the flattened prompt. It sends
`num_ctx` and an output limit mapping to `num_predict` for admitted profiles.
The same check applies independently to fallback candidates. A capacity error
returns HTTP 413. Auto and Compact retain the compatibility behavior on an
unprofiled primary and report `unknown_legacy_primary`. Fallbacks for those
modes require profiles. Custom ordinary requests independently verify the
serving Ollama candidate. The serving-model trace includes provider usage.

## Run an 8,192-byte experiment with an administrative profile

1. Verify the operator's selected endpoint, model digest, usable window and
   template overhead for this deployment. The [November 12 capture](/DOCS/test_results/2026-11-12-345-round2.md)
   observed Qwen3:4b at 16,384 tokens. It does not calibrate today's runner
   or the separate `local` fallback. Check the registry's resolved aliases,
   including runtime model overrides. For each eligible fallback supply its
   own calibrated profile. The shipped registry contains no calibrated profiles.
2. For a verified **16,384-token** runner, set the orchestrator environment
   to `OUTPUT_RESERVE_TOKENS=2048` and `MAX_EVIDENCE_BYTES=8192`.
   Longer queries can reduce the effective allowance. Keep the primary
   profile's `window_tokens` at the independently verified value. Install the
   full models YAML, including its existing aliases and the new profile, at
   the LLM service's `MODELS_CONFIG_PATH` inside the container. Apply settings
   through the [operator's release process](/DOCS/deployment/production-docker-compose.md).
3. Use the same query, repository, generation and model for both arms. For
   the larger arm send `"context_mode":"custom","max_evidence_bytes":8192`
   to `POST /v1/rag`. Require `effective_evidence_bytes=8192` in
   `retrieval_plan.evidence_budget`. Whole-passage delivery may use less.
   For a generated answer, verify the recorded serving model, capacity method
   and digest. Under the example
   profile, the full prompt upper bound including template overhead must be
   at most 14,336 tokens, leaving 2,048 for output. A 413, a smaller effective
   allowance, or an unexpected serving model does not qualify as this arm.
   Record runner context, provider usage and latency with the result.
