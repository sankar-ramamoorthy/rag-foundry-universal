# Free-provider live verification (2026-09-13)

Status: informational record. Findings from this session fed three issues (#122 pre-existing,
#123, #124, #125) — this note is the "what was actually observed live" record they cite back to,
not a decision doc itself.

## Context

Following issue #120 (direct `run_rag()` model passthrough, PR #121), the prod stack
(`100.105.24.12`, ports 8001-8004) was re-ingested with this repo and used to verify, live, whether
each configured free/low-cost provider actually works end-to-end through `run_rag()` — not just
whether it's *listed* in `GET /v1/models`'s catalog.

## What was tried

For each provider, `run_rag()` was called directly (not through the HTTP API) against the
freshly-ingested `rag-foundry-universal` repo (`repo_id=f7641840-ba13-5f9d-9ae6-87e1f924709d`),
with `model=` set to a raw LiteLLM string, bypassing named aliases/slots entirely (the #120
guarantee).

### Groq
Works, but flaky per-model: which specific Groq model actually completes a generation shifts
between runs (`allam-2-7b`, `groq/compound`, `groq/compound-mini`, `openai/gpt-oss-120b` all 503'd
at least once; `openai/gpt-oss-20b` succeeded on one run, a different model on another). Consistent
with a shared free-tier pool under variable load, not a config bug.

### NVIDIA NIM (direct, `nvidia_nim/*`)
**Every** model tried (13+ distinct catalog entries, including well-known chat models like
`meta/llama-3.1-nemotron-70b-instruct`) failed identically. Root-caused to two separate bugs, both
filed:
- [#123](https://github.com/sankar-ramamoorthy/rag-foundry-universal/issues/123) — `llm_client`'s
  fallback-chain error message only reports the **last** attempted model's error, masking whatever
  NIM's real failure actually was.
- [#124](https://github.com/sankar-ramamoorthy/rag-foundry-universal/issues/124) — the local Ollama
  fallback target, `phi4-mini:latest`, isn't pulled on the prod Tailscale host (`GET /api/tags`
  confirmed only `Qwen3:4b, deepseek-r1:7b, granite4:350m, lfm2.5-thinking:1.2b,
  mxbai-embed-large:latest, qwen2.5-coder:*, qwen3.5:4b`), so even the safety net fails.

NIM's actual root cause (bad/expired key, wrong `api_base`, network egress) is still unknown as of
this note — #123 needs to land before it's diagnosable from the API response alone.

### OpenRouter free models
Works well. Confirmed via real `run_rag()` calls (real retrieval + generation, not just a raw
`/generate` probe):
- `openrouter/nvidia/nemotron-3-ultra-550b-a55b:free` — success, `cost_usd: 0.0`, real answer
  grounded in 24 retrieved sources.
- `openrouter/nvidia/nemotron-3-super-120b-a12b:free` — success.
- `openrouter/cohere/north-mini-code:free` — success (first hit when iterating the OpenRouter free
  catalog in listed order).
- `openrouter/poolside/laguna-s-2.1:free` — failed with a genuine upstream 429
  (`RateLimitErrorCategory.VENDOR_RATE_LIMIT`, "temporarily rate-limited upstream... shared pool"),
  not a config problem.

**Practical takeaway:** for a reliable $0 default right now, prefer
`openrouter/nvidia/nemotron-3-ultra-550b-a55b:free` over Groq (less rotation) or NIM (currently
broken).

## Generation-quality side note

The same question run through both `ollama/qwen3:4b` (remote Tailscale Ollama) and
`openrouter/nvidia/nemotron-3-ultra-550b-a55b:free` against identical retrieval (same 24 sources)
produced a real, reproducible instance of the exact failure mode already logged in
`DOCS/test_results/2026-09-13-clean-specimen-canonical-to-document-mapping.md`: qwen3:4b fabricated
a citation (`GraphAssembler._link_docs_to_code`, a `doc:123` prefix scheme — neither exists in the
codebase) despite the correct evidence being present in its context, while the Nemotron model
correctly identified `canonical_to_document_map_http()` and the actual POST-not-GET graph lookup
(issue #107). This is a generation/model-choice failure, not a retrieval failure — relevant to the
WP-Q0 evaluation methodology ([[../audit/08-RAG-Quality-Evaluation-Methodology]]).

## What this fed

- [#122](https://github.com/sankar-ramamoorthy/rag-foundry-universal/issues/122) (filed earlier the
  same session, unrelated root cause) — `codebase_queries`/`codebase_utils` freezing
  `INGESTION_SERVICE_URL` at import time.
- #123, #124 above.
- [#125](https://github.com/sankar-ramamoorthy/rag-foundry-universal/issues/125) — WP-M8,
  transient-error-aware retry/backoff, prompted directly by watching Groq/OpenRouter rate-limit
  errors get the same blind non-backing-off retry as NIM's permanent failures. See
  [[../audit/06-LLM-Provider-LiteLLM-Plan#WP-M8 — Transient-error-aware retry/backoff (2026-09-13, shipped, issue #125)|WP-M8]].
