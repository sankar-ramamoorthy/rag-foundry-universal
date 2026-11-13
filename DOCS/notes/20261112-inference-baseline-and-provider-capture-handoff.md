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
| Deployed runtime | llm_service at `82b70cd` per the Step 0 capture (2026-11-12); previously `8bc0ed2` (`prod-2026-11-11-0300pm`) |
| Ollama | 0.32.1 |
| Model | `Qwen3:4b`, digest `359d7dd4bcdab3d8…`, Q4_K_M, 4.0B; model maximum context 262,144; reasoning ("thinking") capable |
| Modelfile parameters | temperature 0.6, top_k 20, top_p 0.95, repeat_penalty 1; **no `num_ctx`, no seed** (unseeded runs are not reproducible) |
| KV-cache shape | 36 layers, 8 KV heads, key/value length 128 → about 144 KiB per token at fp16 (arithmetic, not measured) |
| Adapter | LiteLLM `ollama/` → `/api/generate`, with system and user messages **flattened** into one `### System:` / `### User:` prompt string; `options: {}`. `ollama_chat/` → `/api/chat` with roles preserved. Ollama's template only emits a system block for a real system role, so with `ollama/` the instructions arrive inside the user turn. |
| Raw response | For `ollama/`, LiteLLM discards `thinking` and `done_reason`; only the wire capture (#344) keeps them |
| Deployed evidence budget | `context_budget` = 4,096 **UTF-8 bytes** (about 1,000-1,150 real tokens). The `max_total_tokens` default is the binding limit; `CONTEXT_WINDOW_TOKENS` 8192 is not. The #342 questions had 26-37 KB of candidates before the cut (85-89% dropped). |
| E1 token usage | 969-1,154 prompt tokens; 1,476-5,223 completion tokens (mostly reasoning); totals up to 6,346 |
| LiteLLM version | Root `uv.lock` pins 1.93.0, but `llm_service/uv.lock` has no `litellm` entry. A fresh container built from current code resolved **1.109.1** (fresh resolution at start, #41). **Deployed: 1.109.1** (Step 0 capture). |
| Also on the host | `qwen3.5:4b` (out of scope) |

## Open hypotheses

The first one is now settled; the second is still open.

- **Settled 2026-11-12: the effective `num_ctx` is 4,096.** It was smaller than
  E1's 6,346-token totals. Original hypothesis: **the effective `num_ctx` may be smaller than the 6,346-token totals**, in which
  case Ollama would drop the oldest tokens during long reasoning output and
  could lose the evidence. This depends on Ollama's default and the host's
  `OLLAMA_CONTEXT_LENGTH`. With capture enabled, each record's
  `environment.ollama.ps_after_call[0].context_length` settles it.
- **Flattened prompts may degrade instruction-following** compared with a real
  system role. #345 Step 2 tests this.

## State of the work

- **#344 (capture): done.** PR #346 was merged on 2026-11-12 as
  `215d095ee0ac851d0215a6ebc6fe4f4b7cad7d61`, and #344 is closed. Capture is
  off by default (`LLM_PROVIDER_CAPTURE_DIR`); the replay tool is
  `scripts/replay_llm_capture.py`. Before merge, a security review fixed path
  traversal through `X-Trace-Id`, capture delaying responses, setup failures
  failing generation, credential echo, file permissions, size and total caps,
  and retention (see the PR #346 review comment). It was verified with stub
  tests and a Linux container. It is deployed (2026-11-12) and off.
- **#345 Step 0: done (2026-11-12).** Production was deployed at `82b70cd`
  with capture enabled for one query and then disabled again. Findings:
  effective `num_ctx` 4,096; LiteLLM 1.109.1; prompt 1,112 and completion
  1,827 tokens; `done_reason: stop`. The query's context was historical
  documentation, not implementation. The record is indexed in
  `raw-index.json` (`2026-11-12-345-step0/`).
- **#345 pilot: done (2026-11-12, owner-authorized GPU).** See
  [results](/DOCS/test_results/2026-11-12-345-inference-pilot.md). Reviewed
  implementation evidence gave a correct trace 4/4; the captured evidence
  gave a correct refusal 6/6 at 4K, 8K and 16K. 8K overflows silently with
  the larger evidence; 16K fits in 4.75 GiB. The runner is
  `scripts/inference_pilot_345.py` (fidelity gate, `--dry-run`,
  `--authorized`). Round 1's raw records were deleted locally along with a
  temporary worktree, but the summary values survive in the report.
- **#345 round 2: done (2026-11-12, owner-authorized GPU).** See
  [results](/DOCS/test_results/2026-11-12-345-round2.md). At 16K:
  - Distracting documentation did not stop the trace (4/4 built it from the
    implementation; 2 correct, 2 partial).
  - `ollama/` versus `ollama_chat/` showed no demonstrable difference.
  - The `/api/embed` omission is inconsistent salience, not missing
    evidence: the witness was present and, with the factory variant,
    complete.
  - **Seeded runs are not reproducible across sessions.** Prompt-cache
    state is the likely confound, so future runs must control and record it.
- **#345 round 3: done (2026-11-12, owner-authorized).** See
  [results](/DOCS/test_results/2026-11-12-345-round3-repro-and-retrieval.md).
  - **Reproducibility:** with the cache condition fixed, output is
    byte-identical. With only the cache state changed, the same request
    gives different answers, including whether `/api/embed` is named.
  - **Arm state:** future arms must start from a verified cold cache. Check
    `prompt_eval_duration` (a full re-evaluation); `/api/ps` after an unload
    request is unreliable.
  - **Retrieval (#342):** the Step 0 pool is 38 Markdown chunks with no
    Python. Graph expansion added 0 documents. The implementation witnesses
    rank 676 to beyond 2,000 by vector similarity, so this is a ranking
    failure, not truncation.
  - **Budgeting (#194):** a larger budget would add only more documentation
    for this query.
  - The local reproduction matches production's first 3,950 bytes, but adds
    a 3-byte chunk. Production pool or budget settings would explain it;
    the operator can check them read-only.
- **#349 (context-pressure and overflow diagnostics):** filed and refined
  after owner review. It separates prompt overflow from generation-time
  pressure, and context sensitivity from verified truncation. It is
  observational and not started.
- **#345 Steps 1-3:** the [draft inference-baseline protocol](/DOCS/evaluations/2026-11-12-inference-baseline-protocol.md)
  describes them. It is not frozen and not authorized; the GPU arms need the
  owner's explicit approval.
- **No production configuration has changed.** Production defaults stay as
  they are throughout #345. Experiment arms vary settings only in replayed
  provider requests.

### Deployment facts verified for the runbook (2026-11-12)

- The rendered production Compose config (`docker-compose.yml` +
  `docker-compose.prod.yml`) at `215d095` passes `LLM_PROVIDER_CAPTURE_DIR`
  from `.env` to llm_service (`env_file`). llm_service's only production mount
  is `./volumes/llm-runtime` → `/runtime` (read-write). The container runs as
  root (the image sets no `USER`), so records are root-owned `0600` on the
  host: read and copy them with `docker exec` and `docker cp`, not `sudo`.
- `.env` and `volumes/` are gitignored, so enabling capture does not trip
  `prod-refresh.sh`'s clean-tree check.
- `prod-refresh.sh --deploy` runs a `/v1/rag` smoke query against repo
  `f7641840-…` (generation `ready` at ingested commit `8e063350`, checked
  2026-11-12). With capture enabled, that query is the Step 0 capture. Its
  curl timeout is 60 s; if it times out, the generation still finishes and
  the record is still written.
- `docker-compose.prod.yml` requires `GIT_SHA` and `BUILD_DATE` to be set
  even for `up --no-build`; the runbook sets them for the single-service
  recreate that disables capture.
- Of the six E1 fixed contexts (4,096 bytes), three contain **none** of their
  case's answer-key identifiers (L1, L2, F3) and only F1 and L3 contain all of
  theirs. Fixed 4 KB inputs can therefore test eviction and the adapter, but
  not whether more evidence helps (see the protocol).

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

## Pending owner decisions

- Steps 3-4 (16 KB and 32 KB evidence packages graded on the full call path)
  have not started. Round 3 shows that the actual candidates contain no
  witnesses, so the packages would have to be constructed. Defining a
  realistic construction is a design decision for the owner; see
  [round 3](/DOCS/test_results/2026-11-12-345-round3-repro-and-retrieval.md).
- Optional read-only operator check: `MAX_TOTAL_CHUNKS`,
  `CONTEXT_WINDOW_TOKENS`, `PROMPT_RESERVE_TOKENS` and `OUTPUT_RESERVE_TOKENS`
  in the production `.env`, to explain the 3-byte fidelity gap.
- When to start #349 (no GPU needed for the classifier itself).
- No production tuning has been proposed.

Capture is disabled on production. Use the
[runbook](/DOCS/deployment/2026-11-12-capture-deploy-and-step0-runbook.md)
pattern again if another capture is needed.

## Known local test noise

`llm_service` tests `test_models_endpoint_universal_without_remote_env` and
`test_no_params_uses_local_ollama_default` fail on untouched `main` on the
owner's Windows machine (the cause appears environment-dependent). They are
not caused by #344.
