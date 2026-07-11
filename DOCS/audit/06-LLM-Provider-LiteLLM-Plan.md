---
title: "LLM Provider Plan — LiteLLM & Model Switching"
date: 2026-07-09
type: audit-plan
status: proposed
effort: "2–3 days core, +2 days ops polish"
tags:
  - audit
  - llm
  - litellm
  - rag-foundry
related:
  - "[[05-Enterprise-Platform-Plan]]"
  - "[[00-Audit-Overview]]"
---

# 🔌 LLM Provider Plan — LiteLLM & Model Switching

> [!abstract] Goal
> Replace the hardcoded Ollama call with **LiteLLM**, giving config-driven access to OpenAI, Anthropic, Azure OpenAI, Bedrock, Google, and local Ollama — with per-request model switching, fallbacks, streaming, and cost tracking.

## 1 · Current state (why this is easy)

The entire LLM integration is **one function**: `llm_service/src/core/llm_client.py::generate_completion` (41 lines). It:
- raises `ValueError` for any provider except `"ollama"` (line 22)
- builds a naive `"Context:\n…\n\nQuestion:\n…"` prompt (line 24) — no system prompt, no template versioning
- calls Ollama `/api/generate` non-streaming with a 600 s timeout

Upstream, `rag_orchestrator` already passes optional `provider`/`model` query params through (`service.py:282-289`, `routes.py`) — the plumbing for per-request switching **already exists** end to end. Only the bottom of the stack is rigid. The embedder factory (`shared/embedders/factory.py`) is a separate concern — keep embeddings on their current path for now (see §5).

## 2 · Architecture decision

> [!important] Recommendation: **LiteLLM Python SDK inside `llm_service`** (Option A), with the LiteLLM **Proxy** as an optional later deployment mode (Option B).
>
> - **Option A — SDK in-process:** `litellm.acompletion(model=…)` inside the existing service. Keeps the service boundary you already have (every other service calls `llm_service`, not vendors), no new container, full control. *Choose this.*
> - **Option B — LiteLLM Proxy sidecar:** standalone gateway with virtual keys, per-team budgets, admin UI. Adopt **when** [[05-Enterprise-Platform-Plan#WP-E3 — Identity & multi-tenancy|multi-tenancy]] needs per-team spend controls — `llm_service` then just points its OpenAI-compatible client at the proxy URL. The SDK work in Option A is not thrown away; only the base URL and key handling change.

`llm_service` survives as the seam that owns prompt templates, guardrails, and (later) response caching — do not let other services call LiteLLM directly.

## 3 · Work packages

### WP-M1 — LiteLLM core swap
**Goal:** any LiteLLM-supported model works via `provider`/`model` params; Ollama remains the default; behavior otherwise unchanged.
**Files:** `llm_service/src/core/llm_client.py`, `llm_service/src/core/config.py`, `llm_service/pyproject.toml`, `llm_service/src/api/v1/main.py` (models in `models.py`).
**Directions:**
- Add `litellm` dependency. Replace the body of `generate_completion` with `litellm.acompletion(model=model_string, messages=[…])`.
- **Model registry in config, not code:** a `models.yaml` (mounted/env-pointed) mapping friendly aliases → LiteLLM model strings + params:
  ```yaml
  models:
    default: ollama/granite4:350m
    fast:    anthropic/claude-haiku-4-5
    smart:   anthropic/claude-sonnet-5
    gpt:     openai/gpt-5.1
  fallbacks:
    smart: [gpt, default]
  ```
  Resolve incoming `model` param against aliases first, else pass through verbatim (power users can send raw LiteLLM strings). `provider` param becomes advisory/deprecated — LiteLLM's `provider/model` string subsumes it; keep accepting it for backward compat by mapping `(provider, model) → "provider/model"`.
- Proper message structure: system prompt (extract the current context-stuffing into a versioned template, e.g. `prompts/rag_answer.v1.txt`) + user message. Template name/version goes into the response metadata for eval reproducibility.
- API keys via env only (`OPENAI_API_KEY`, `ANTHROPIC_API_KEY`, …) — LiteLLM reads them natively; document in `.env.example`. Never accept keys in requests.
- Config: `OLLAMA_BASE_URL` → LiteLLM `api_base` for `ollama/…` models; sane timeout (e.g. 120 s) with per-model override in yaml.
- Return shape: keep `{provider, model, response}` for compatibility; add `usage` (prompt/completion tokens from LiteLLM) and `model_alias`.
**Acceptance criteria:**
- [ ] `/generate` with no params answers via Ollama exactly as before (regression test with respx/mock)
- [ ] `/generate?model=smart` routes to the aliased model (mock-asserted model string)
- [ ] Raw string `model=anthropic/claude-sonnet-5` passes through
- [ ] Unknown alias → 400 with the list of valid aliases
- [ ] Response includes token `usage`; existing llm_service tests still pass

### WP-M2 — Resilience: fallbacks, retries, timeouts
**Goal:** provider outages degrade gracefully instead of 500ing the RAG pipeline.
**Directions:** use `litellm.Router` with the yaml's `fallbacks` map, `num_retries=2`, exponential backoff, per-model `timeout`. Circuit-note in logs when a fallback fires (structured field `fallback_from`). Surface the *actually used* model in the response so the UI can display it.
**Acceptance criteria:**
- [ ] Primary model mocked to fail → answer arrives from fallback; response names the fallback model
- [ ] All providers down → 503 with actionable message (not a stack trace)
- [ ] Timeout respected per model (test with delayed mock)

### WP-M3 — Streaming
**Goal:** token streaming end-to-end for the web UI ([[05-Enterprise-Platform-Plan#WP-E6 — Product web UI (replace Gradio)|WP-E6]]).
**Directions:** new `POST /generate/stream` returning SSE (`text/event-stream`), backed by `litellm.acompletion(stream=True)`; orchestrator gains `/v1/rag/stream` that performs retrieval then proxies the token stream, emitting a final `sources` event. Non-streaming endpoints remain.
**Acceptance criteria:**
- [ ] `curl -N` on `/v1/rag/stream` shows incremental tokens followed by a terminal `sources` event
- [ ] Client disconnect cancels the upstream LLM call (assert via mock cancellation)

### WP-M4 — Cost & usage telemetry
**Goal:** per-request cost visibility; the enterprise chargeback hook.
**Directions:** LiteLLM's `completion_cost()` + usage callbacks → structured log + Prometheus counters (`llm_tokens_total{model,team}`, `llm_cost_usd_total{model,team}`); persist per-request usage rows (model, tokens, cost, user/team once [[05-Enterprise-Platform-Plan#WP-E3 — Identity & multi-tenancy|WP-E3]] lands). When/if Option B (proxy) is adopted, budgets/virtual keys replace the homegrown accounting — keep this layer thin.
**Acceptance criteria:**
- [ ] Every `/generate` logs model, tokens, and computed cost
- [ ] Metrics visible in the Grafana dashboard from [[05-Enterprise-Platform-Plan#WP-E5 — Observability|WP-E5]]

### WP-M5 — Model switching in the product surface
**Goal:** users pick models per query; admins define the menu.
**Directions:** orchestrator `/v1/rag` already accepts `model` — plumb an allowed-alias list endpoint (`GET /v1/models` on llm_service reading the yaml) → UI dropdown (Gradio now, React later). Optional per-repo default model in repo settings. Summarization path (`/v1/summarize/{id}`) gets the same treatment — it currently bypasses configuration.
**Acceptance criteria:**
- [ ] `GET /v1/models` lists aliases + which is default
- [ ] Gradio dropdown switches models; answer metadata shows the model used
- [ ] Summarize endpoint honors model alias

## 4 · Sequencing

WP-M1 → WP-M2 (same PR acceptable) → WP-M5 (small) → WP-M3 → WP-M4. Total ≈ 4–5 agent-days. No migrations, no schema changes, no other service's code touched except the two orchestrator endpoints (stream + models passthrough).

## 5 · Explicit non-goals (for now)

- **Embeddings via LiteLLM** — possible (`litellm.embedding`), but embedding-model change invalidates every stored vector (dimension + space). Keep `mxbai-embed-large` fixed; treat embedding-model migration as its own project with a re-embedding job and per-index model tagging. Note the existing 768/1024 inconsistency ([[01-Codebase-Audit-Findings#F-14|F-14]]) must be fixed regardless.
- **LLM-driven retrieval routing** — deferred by ADR-045; keep deterministic traversal selection.
- **Response caching** — worthwhile later at the `llm_service` seam (semantic cache), after usage data from WP-M4 shows repeat-query rates.
