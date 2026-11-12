---
title: "LLM Provider-Request Capture and Replay"
type: deployment-guide
status: accepted
date: 2026-11-12
tags: [observability, llm, ollama, litellm, diagnostics, issue-344]
related:
  - "[Agent Execution Boundaries](/DOCS/deployment/agent-execution-and-verification.md)"
  - "[Production Docker Compose Release Process](/DOCS/deployment/production-docker-compose.md)"
  - "[WP-T1 retrieval evidence trace](/DOCS/audit/WP-T1-retrieval-evidence-trace.md)"
---

# LLM Provider-Request Capture and Replay

Issue #344. This is an opt-in diagnostic that records exactly what llm_service
sends to the inference provider and what comes back. WP-T1 traces evidence up
to `final_context_manifest`; this capture covers the next step, from
llm_service to the provider.

## Why it exists

Two things happen after the orchestrator's `/generate` request that its trace
cannot see:

- LiteLLM's `ollama/` route posts to `/api/generate` and **flattens** the
  system and user messages into one `prompt` string (`### System:` /
  `### User:` headers). Ollama then wraps that string in the model's chat
  template as a single user turn. `ollama_chat/` keeps the roles and posts to
  `/api/chat`.
- llm_service sends `options: {}`, so `num_ctx`, temperature, seed and
  thinking take the server and Modelfile defaults.

LiteLLM also discards parts of the raw `/api/generate` response, including
the `thinking` text and `done_reason`. The capture keeps them.

## Enabling

Capture is off unless `LLM_PROVIDER_CAPTURE_DIR` is set in llm_service's
environment. With the existing Compose files, `./volumes/llm-runtime` is
already mounted at `/runtime`, so you only need to add one line to `.env`:

```
LLM_PROVIDER_CAPTURE_DIR=/runtime/provider-captures
# optional, default 8000000: larger records drop bodies but keep hashes
LLM_PROVIDER_CAPTURE_MAX_BYTES=8000000
```

Then recreate llm_service (`docker compose ... up -d llm_service`). On the
production host this is an operator action and changes the running release's
configuration. See [Agent Execution Boundaries](/DOCS/deployment/agent-execution-and-verification.md).
To disable capture, remove the line and recreate the container.

**Sensitivity:** records contain the full prompt, including repository source
text. Authorization and API-key headers are redacted. Treat the capture
directory like raw evaluation captures: keep it out of git, and copy records
you need as evidence into `DOCS/test_results/_raw/`, indexed in
`raw-index.json`. Delete records when the investigation ends; there is no
automatic retention.

## What a record contains (`llm_provider_capture.v1`)

There is one JSON file per fallback candidate:
`<dir>/<UTC date>/<trace_id>-<capture_id>.json`.

| Field | Meaning |
|---|---|
| `trace_id`, `repo_id`, `generation_id` | From the orchestrator's `X-Trace-Id` / `X-Repo-Id` / `X-Generation-Id` headers; join to the `/v1/rag` response's `trace_id` and `retrieval_plan` |
| `application_input` | Pre-transform messages, prompt template version, context/query sha256 and size |
| `provider_request` | The provider body as LiteLLM built it (pre-API-call hook; all providers) |
| `wire.exchanges[]` | Ollama routes only: the exact request bytes and the raw response, one entry per transient retry |
| `result` | Status, latency, finish reason, usage, error |
| `environment` | LiteLLM version, llm_service git sha, Ollama version, model digest, Modelfile parameters, template sha256, and `ps_after_call` (the loaded runner's effective `context_length` and VRAM) |
| `not_observable` | The provider-side template rendering and tokenization, which are not visible from llm_service |
| `omitted` | Present only when the size limit dropped bodies; lists the sha256 of each dropped body |

An empty `options` means the value was not sent, not that it is zero. The
effective value is whatever the server or Modelfile defaults to, and for
context length it is visible in `ps_after_call`.

## Replay

```
python scripts/replay_llm_capture.py CAPTURE.json
python scripts/replay_llm_capture.py CAPTURE.json --set-option num_ctx=16384
python scripts/replay_llm_capture.py CAPTURE.json --api-base http://other:11434
```

Without overrides, the captured bytes are sent unchanged. Overrides are listed
in the `llm_provider_replay.v1` record, and `body_identical` becomes false.
The record also lists environment differences between capture time and now.
**Replay runs real inference**: against a shared or production Ollama it uses
GPU time, so run it deliberately.

## Verification performed (2026-11-12)

- Unit tests (`llm_service/tests/core/test_provider_capture.py`) run against a
  local stub Ollama server and compare the bytes it received with the captured
  wire bytes and the pre-call body, for both `ollama/` and `ollama_chat/`.
  They also cover disabled-by-default, provider failure with retries,
  credential redaction (a real Bearer header sent and absent from the record),
  the size limit, and capture-write failure not failing generation.
- Container check: the llm_service image built from the #344 branch, with
  capture enabled and pointed at a stub Ollama container, produced a record
  whose wire bytes matched the stub's received bytes exactly. The `/generate`
  response shape was unchanged. That container resolved **LiteLLM 1.109.1**,
  not the root lock's 1.93.0. The container resolves dependencies fresh at
  start (#41), so the running LiteLLM version must be read from records, not
  assumed.
