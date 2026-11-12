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
# optional settings, shown with their defaults:
LLM_PROVIDER_CAPTURE_MAX_BYTES=8000000          # hard per-record bound
LLM_PROVIDER_CAPTURE_MAX_TOTAL_BYTES=1000000000 # capture stops when the directory would exceed this
LLM_PROVIDER_CAPTURE_RETENTION_DAYS=7           # day directories older than this are deleted; 0 = keep
```

Then recreate llm_service (`docker compose ... up -d llm_service`). On the
production host this is an operator action and changes the running release's
configuration. See [Agent Execution Boundaries](/DOCS/deployment/agent-execution-and-verification.md).
To disable capture, remove the line and recreate the container.

## Safety properties

- **Off by default.** Nothing is recorded unless `LLM_PROVIDER_CAPTURE_DIR`
  is set.
- **Never interrupts or delays generation.** If capture setup fails, the
  normal call runs uncaptured. The record is completed and written in a
  background task, so a slow or unreachable Ollama metadata endpoint cannot
  delay the `/generate` response. Write errors are logged and dropped.
  Records still pending when the container stops are lost.
- **Source code at rest.** Records contain the full prompt, including
  repository source text, in plaintext. Files are created owner-only (`0600`,
  directories `0700`) with exclusive create, so nothing is overwritten. Keep
  the directory out of git. If you need a record as evidence, copy it into
  `DOCS/test_results/_raw/` and index it in `raw-index.json`; retention will
  otherwise delete it. Records also contain the provider's `api_base` host:
  do not paste them into tracked docs.
- **Credentials.** Sensitive headers (`Authorization`, API-key headers,
  cookies) and credential-like URL query parameters (`key`, `api_key`,
  `token` and similar) are redacted. Values of credential-like environment
  variables (names containing KEY, TOKEN, SECRET, PASSWORD or CREDENTIAL,
  8+ characters) are scrubbed from the whole record. That covers a provider
  echoing a key in an error body or exception message.
- **Caller headers are data, never paths.** `X-Trace-Id` and the other
  correlation headers are recorded as field values only. File names come
  solely from the server-generated `capture_id`.
- **Bounded disk use.** `LLM_PROVIDER_CAPTURE_MAX_BYTES` is a hard bound on
  each record. Over it, bodies are dropped and replaced by their sha256. If
  the record is still too large, only ids, sizes and hashes are kept. The
  total cap stops capturing, never generation, and day directories past the
  retention period are deleted. Only `YYYY-MM-DD` directories are pruned;
  anything else in the capture directory is left alone.
- **Not covered:** llm_service's port is unauthenticated (this predates the
  capture). While capture is enabled, any caller that can reach `/generate`
  can cause records to be written, within the caps above. Enable capture
  only for an investigation, and disable it afterwards.

## What a record contains (`llm_provider_capture.v1`)

There is one JSON file per fallback candidate:
`<dir>/<UTC date>/<capture_id>.json`.

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
- Security review of PR #346 (same day): nine defects were confirmed with
  tests that failed before the fixes:
  - caller-controlled path traversal through `X-Trace-Id`
  - capture metadata calls delaying the response
  - capture-setup failures failing generation
  - a per-record size limit that was not a hard bound
  - credentials echoed in error bodies
  - no owner-only permissions
  - no total cap
  - no retention
  - URL query credentials

  All are fixed and covered by tests. A Linux container re-check sent a
  hostile `X-Trace-Id` of `../../../tmp/pwn`, set a real API key in the
  environment, and slowed the stub's metadata endpoints to 2 s. Results:
  `/generate` answered in 0.72 s; no file was created outside the capture
  directory; records were `600` and directories `700`; the key was sent,
  recorded as `<redacted>`, and absent from every file.
