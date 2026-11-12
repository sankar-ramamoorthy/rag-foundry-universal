---
title: "Runbook: deploy #346 with provider capture, record #345 Step 0, disable capture"
date: 2026-11-12
type: deployment-guide
status: current
tags: [deployment, runbook, llm, capture, issue-344, issue-345]
related:
  - "[Production Docker Compose Release Process](/DOCS/deployment/production-docker-compose.md)"
  - "[LLM Provider-Request Capture and Replay](/DOCS/deployment/llm-provider-request-capture.md)"
  - "[Agent Execution Boundaries](/DOCS/deployment/agent-execution-and-verification.md)"
  - "[Inference-side handoff](/DOCS/notes/20261112-inference-baseline-and-provider-capture-handoff.md)"
  - "[Draft inference-baseline protocol](/DOCS/evaluations/2026-11-12-inference-baseline-protocol.md)"
---

# Runbook: deploy #346 with capture, record Step 0, disable capture

This is a one-time operator procedure for #345 Step 0, run on the production
host from the production checkout. It uses the existing
`scripts/prod-refresh.sh` and adds no new deployment mechanism.

- **Ref:** `215d095ee0ac851d0215a6ebc6fe4f4b7cad7d61` (PR #346; the only change
  since the running `8bc0ed2`).
- **Cadence:** this qualifies as an ad hoc refresh under category 2,
  observability blocker, because #345 cannot proceed without it. That is the
  operator's judgment ([release guide](/DOCS/deployment/production-docker-compose.md),
  "Deployment cadence"). The suggested label is `prod-hotfix-2026-11-12-344`.
- **Runtime effect:** a new llm_service and orchestrator image, with capture
  enabled only for the deploy's own smoke query and then disabled. No
  production default changes. No migration; the script never runs one, and
  #346 adds none.

The verified preconditions are listed in the
[handoff note](/DOCS/notes/20261112-inference-baseline-and-provider-capture-handoff.md#deployment-facts-verified-for-the-runbook-2026-11-12).

## Part 1: read-only diagnostics (changes nothing)

```bash
git status --short; git log --oneline -1         # expect: clean, 8bc0ed2
grep -c '^LLM_PROVIDER_CAPTURE' .env              # expect: 0
nvidia-smi --query-gpu=name,memory.total,memory.used --format=csv,noheader
# Ollama server settings (num_ctx default, parallelism, keep-alive):
systemctl show ollama -p Environment 2>/dev/null | tr ' ' '\n' | grep -i '^ollama_'
cat /etc/systemd/system/ollama.service.d/*.conf 2>/dev/null | grep -i ollama_
# if Ollama runs in Docker instead of systemd:
# docker inspect <ollama-container> --format '{{range .Config.Env}}{{println .}}{{end}}' | grep -i '^ollama_'
```

Paste this output back. An empty Ollama settings result is itself
informative: it means the server is using its built-in defaults.

## Part 2: deploy with capture enabled (modifies the deployment)

```bash
echo 'LLM_PROVIDER_CAPTURE_DIR=/runtime/provider-captures' >> .env
scripts/prod-refresh.sh --ref 215d095ee0ac851d0215a6ebc6fe4f4b7cad7d61 \
  --release prod-hotfix-2026-11-12-344 --deploy
```

The script builds the images, verifies provenance and mounts, deploys, checks
health, and runs its RAG smoke query. That query is the "one normal RAG
query" for Step 0 and is captured. If the smoke step reports a timeout (the
curl limit is 60 s), the deploy itself has still completed. Wait about two
minutes so the generation finishes and its record is written, then continue.

## Part 3: read the Step 0 record (read-only)

This prints only metadata: no prompt, source text or answer text.

```bash
docker exec -i llm-service python3 - <<'EOF'
import glob, json, os
paths = sorted(glob.glob("/runtime/provider-captures/*/*.json"), key=os.path.getmtime)
print("records:", len(paths))
r = json.load(open(paths[-1]))
env, ex = r["environment"], (r.get("wire") or {}).get("exchanges") or [{}]
body = (r.get("provider_request") or {}).get("body") or {}
resp = ((ex[-1].get("response") or {}).get("body_json")) or {}
print(json.dumps({
  "trace_id": r["trace_id"], "repo_id": r["repo_id"], "generation_id": r["generation_id"],
  "model": r["attempt"]["model"], "route": r["attempt"]["route"],
  "litellm_version": env.get("litellm_version"), "llm_service_git_sha": env.get("llm_service_git_sha"),
  "ollama": {k: (env.get("ollama") or {}).get(k) for k in ("version", "tag", "show", "ps_after_call")},
  "request": {"url_path": "/" + (r.get("provider_request") or {}).get("url", "").split("/", 3)[-1],
              "body_keys": sorted(body), "options": body.get("options"),
              "flattened_system_prompt": str(body.get("prompt", "")).startswith("### System:"),
              "context_bytes": r["application_input"]["context_bytes"]},
  "response": {k: resp.get(k) for k in ("done_reason", "prompt_eval_count", "eval_count",
               "total_duration", "prompt_eval_duration", "eval_duration")},
  "thinking_chars": len(resp.get("thinking") or ""), "answer_chars": len(resp.get("response") or ""),
  "result": {k: (r.get("result") or {}).get(k) for k in ("status", "finish_reason", "usage", "latency_ms")},
  "exchanges": len(ex), "capture_errors": r.get("capture_errors"),
}, indent=1, default=str))
EOF
nvidia-smi --query-compute-apps=pid,process_name,used_memory --format=csv,noheader
```

Run `nvidia-smi` within about five minutes of the smoke query, while Ollama
still has the model loaded. Paste both outputs back. The key field is
`ollama.ps_after_call[0].context_length`, the **effective `num_ctx`**.

## Part 4: keep the record, disable capture, clean up (modifies)

```bash
mkdir -p ~/rag-foundry-captures
docker cp llm-service:/runtime/provider-captures ~/rag-foundry-captures/2026-11-12-step0
sed -i '/^LLM_PROVIDER_CAPTURE_DIR=/d' .env
GIT_SHA=$(git rev-parse HEAD) BUILD_DATE=unused-no-build RELEASE_VERSION=prod-hotfix-2026-11-12-344 \
  docker compose -f docker-compose.yml -f docker-compose.prod.yml up -d --no-build --no-deps llm_service
docker exec llm-service sh -c 'test -z "$LLM_PROVIDER_CAPTURE_DIR" && echo capture-disabled'
curl -s localhost:8003/version; echo
docker exec llm-service rm -rf /runtime/provider-captures
```

Expected: `capture-disabled`, and `/version` still reporting `215d095…`. The
recreate reuses the image just built; `--no-build` means the `GIT_SHA` and
`BUILD_DATE` values are only there to satisfy the production override's
required-variable check.

The copy in `~/rag-foundry-captures/` contains repository source in
plaintext and is outside the checkout. Keep it until #345 has used it, then
delete it. To make it agent-readable evidence, move it into
`DOCS/test_results/_raw/` on a machine with the repository and index it with
`scripts/raw_index.py`.

## Afterwards

Fill in the release record's **FILL IN** fields as usual. Note there that
capture was enabled for the smoke query only and disabled afterwards.
