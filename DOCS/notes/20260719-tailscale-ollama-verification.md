# Remote Ollama over Tailscale — connectivity verified (2026-07-19)

Status: endpoint verified from the Windows host; container-level and
LiteLLM-boundary verification still pending (tracked in the issue
referenced below).

## What was verified

From Windows PowerShell, the Linux machine's Ollama (GTX 1080 Ti,
11 GB VRAM) answered over Tailscale:

- Endpoint: `http://100.105.24.12:11434/api/generate`
- Model: `Qwen3:4b`
- Result: exact expected completion, `done_reason: stop`
- Timings (cold): total ≈ 5.38 s — model load ≈ 4.20 s, prompt eval
  ≈ 0.66 s, generation ≈ 0.52 s. Warm requests should be markedly
  faster since the load cost dominates.

Connectivity is therefore not the open question. The open questions are
whether the Dockerized stack can reach the same Tailscale address, and
LiteLLM routing through the app boundary.

## Expected payoff

The 1080 Ti mainly buys **model quality and usable context** (GPU-run
4B–8B-class quantized models) rather than raw latency; it may or may
not beat the Windows-local models on speed depending on model size,
warm state, network latency, and context length.

## Remaining verification steps

1. From inside the llm_service container (Docker bridge → Tailscale
   routing is the risk):

   ```
   docker compose exec llm_service python -c "import requests; \
     r = requests.get('http://100.105.24.12:11434/api/tags', timeout=20); \
     print(r.status_code, r.text[:300])"
   ```

2. Through the application boundary, once an alias exists:

   ```
   POST http://localhost:8003/generate?model=remote-local
   ```

   and confirm the response reports `model: ollama/Qwen3:4b` (with
   `model_alias: remote-local`).

## Proposed alias shape (WP-M1 registry already supports this)

```yaml
models:
  remote-local:
    model: ollama/Qwen3:4b
    api_base: http://100.105.24.12:11434
    timeout: 180
```

Caveat: `models.yaml` values are static — the registry has no env-var
interpolation yet, and models.yaml is baked into the llm_service image.
For a machine-specific endpoint, either point `MODELS_CONFIG_PATH` at a
non-committed local yaml, or add env interpolation to the registry
(see the issue).

Related: the standing multi-endpoint requirement (aliases, priorities,
fallbacks, secrets rules) predates this note; see
`DOCS/audit/06-LLM-Provider-LiteLLM-Plan.md` and the issue below.
