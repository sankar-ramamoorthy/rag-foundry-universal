---
title: "Inference-side handoff: provider-request capture (#344) and inference baseline (#345)"
date: 2026-11-12
type: working-note
status: current
tags: [handoff, llm, ollama, litellm, qwen3, num_ctx, observability, issue-344, issue-345]
related:
  - "[Issue #344](https://github.com/sankar-ramamoorthy/rag-foundry-universal/issues/344)"
  - "[Issue #345](https://github.com/sankar-ramamoorthy/rag-foundry-universal/issues/345)"
  - "[PR #346](https://github.com/sankar-ramamoorthy/rag-foundry-universal/pull/346)"
  - "[Issue #342](https://github.com/sankar-ramamoorthy/rag-foundry-universal/issues/342)"
  - "[Issue #194](https://github.com/sankar-ramamoorthy/rag-foundry-universal/issues/194)"
  - "[LLM Provider-Request Capture and Replay](/DOCS/deployment/llm-provider-request-capture.md)"
  - "[Agent Execution Boundaries](/DOCS/deployment/agent-execution-and-verification.md)"
---

# Inference-side handoff (2026-11-12)

This note is written so that anyone resuming the work (a person, Claude Code or
Codex) can do so from the repository alone. Roadmap: Phase 6, E track
(extends WP-T1). It complements, and does not replace, the retrieval-side
investigation in #342.

## Why this work exists

The failures in #342 were investigated only up to the final-context manifest.
Nobody had looked at the next step, the request llm_service sends to the
model. When we did, we found that request may be constraining Qwen3:4b
independently of retrieval. **Until #345 answers this, do not attribute
answer failures to retrieval alone.**

## Verified facts

These were verified on 2026-11-12 from read-only HTTP calls and local code
inspection.

| Item | Value |
|---|---|
| Deployed runtime | All four services at `8bc0ed2` (`prod-2026-11-11-0300pm`) |
| Ollama | 0.32.1 |
| Model | `Qwen3:4b`, digest `359d7dd4bcdab3d8…`, Q4_K_M, 4.0B; model maximum context 262,144; reasoning ("thinking") capable |
| Modelfile parameters | temperature 0.6, top_k 20, top_p 0.95, repeat_penalty 1; **no `num_ctx`, no seed** (unseeded runs are not reproducible) |
| KV-cache shape | 36 layers, 8 KV heads, key/value length 128 → about 144 KiB per token at fp16 (arithmetic, not measured) |
| Adapter | LiteLLM `ollama/` → `/api/generate`, with system and user messages **flattened** into one `### System:` / `### User:` prompt string; `options: {}`. `ollama_chat/` → `/api/chat` with roles preserved. Ollama's template only emits a system block for a real system role, so with `ollama/` the instructions arrive inside the user turn. |
| Raw response | For `ollama/`, LiteLLM discards `thinking` and `done_reason`; only the wire capture (#344) keeps them |
| Deployed evidence budget | `context_budget` = 4,096 **UTF-8 bytes** (about 1,000-1,150 real tokens). The `max_total_tokens` default is the binding limit; `CONTEXT_WINDOW_TOKENS` 8192 is not. The #342 questions had 26-37 KB of candidates before the cut (85-89% dropped). |
| E1 token usage | 969-1,154 prompt tokens; 1,476-5,223 completion tokens (mostly reasoning); totals up to 6,346 |
| LiteLLM version | Root `uv.lock` pins 1.93.0, but `llm_service/uv.lock` has no `litellm` entry. A fresh container built from current code resolved **1.109.1** (fresh resolution at start, #41). The deployed version is unknown until a capture or the operator reports it. |
| Also on the host | `qwen3.5:4b` (out of scope) |

## Open hypotheses

None of these is established yet.

- **Effective `num_ctx` may be smaller than the 6,346-token totals**, in which
  case Ollama would drop the oldest tokens during long reasoning output and
  could lose the evidence. This depends on Ollama's default and the host's
  `OLLAMA_CONTEXT_LENGTH`. With capture enabled, each record's
  `environment.ollama.ps_after_call[0].context_length` settles it.
- **Flattened prompts may degrade instruction-following** compared with a real
  system role. #345 Step 2 tests this.

## State of the work

- **#344 (capture):** implemented in PR #346, awaiting owner review. It is off
  by default (`LLM_PROVIDER_CAPTURE_DIR`), and the replay tool is
  `scripts/replay_llm_capture.py`. It was verified with stub-server unit tests
  and a local container run, but **not yet against the deployed stack**.
- **#345 (experiment):** not started; it depends on #346 being deployed with
  capture enabled. It varies one factor at a time with evidence frozen to
  captured bytes: Step 0, observe the current setup; Step 1, `num_ctx` ∈ {4k,
  8k, 16k, 32k}; Step 2, `ollama/` vs `ollama_chat/` vs direct `/api/chat`;
  Step 3, thinking unset/on/off. It then hands off to #194, the evidence-byte
  budget sweep.
- **No production configuration has changed.**

## Operating boundaries for agents

- **No shell access to the Linux host.** There are no SSH keys, and the owner
  confirmed this; do not attempt Tailscale SSH. Read-only HTTP (`/version`,
  `/health`, Ollama `/api/version|tags|ps`, and `/api/show`, a read-only POST)
  is fine when the owner has asked for verification. The host address comes
  from the gitignored `.env`; never print or commit it.
- **Inference against the Linux Ollama uses its GPU.** Replays and experiment
  arms need the owner's explicit approval. Do not send a test generation just
  to discover `num_ctx`; wait for a capture from an ordinary query.
- **Avoid the local CPU Qwen models**: they are far too slow. Use stub servers
  for fidelity tests, as the #344 tests do.
- Enabling capture on the host, deploying, and changing `.env` are operator
  actions ([Agent Execution Boundaries](/DOCS/deployment/agent-execution-and-verification.md)).

## Pending operator action

This is one consolidated step: the read-only part first, then a config change
once #346 is deployed.

```bash
# read-only
nvidia-smi --query-gpu=name,memory.total,memory.used --format=csv
nvidia-smi --query-compute-apps=pid,process_name,used_memory --format=csv
systemctl show ollama -p Environment 2>/dev/null; cat /etc/systemd/system/ollama.service.d/*.conf 2>/dev/null
# or, if Ollama runs in Docker: docker inspect <ollama-container> --format '{{json .Config.Env}}' | tr ',' '\n' | grep OLLAMA
docker compose exec llm_service uv run --directory /app/llm_service python -c "import importlib.metadata as m; print(m.version('litellm'))"

# after deploying #346: enable capture (config change)
echo 'LLM_PROVIDER_CAPTURE_DIR=/runtime/provider-captures' >> .env
docker compose -f docker-compose.yml -f docker-compose.prod.yml up -d llm_service
```

## Known local test noise

`llm_service` tests `test_models_endpoint_universal_without_remote_env` and
`test_no_params_uses_local_ollama_default` fail on untouched `main` on the
owner's Windows machine (the cause appears environment-dependent). They are
not caused by #344.
