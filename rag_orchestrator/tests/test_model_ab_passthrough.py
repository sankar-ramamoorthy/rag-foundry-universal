# rag_orchestrator/tests/test_model_ab_passthrough.py
"""
Issue TBD: the free-provider (Groq/NIM/OpenRouter) A/B eval harness calls
run_rag() directly with a raw model string, bypassing named
aliases/slots entirely -- see test_run_rag_model_override.py for the
mocked unit-level guarantee that such a string reaches /generate
unchanged.

This is the live counterpart: it proves the guarantee holds against a
*real* llm_service, using whichever free-provider models are actually
live right now -- never hardcoded IDs. That matters because the original
bug this guards against was exactly a hardcoded alias (groq_fast ->
llama-3.1-8b-instant) silently breaking once the provider deprecated the
model; a test that itself hardcodes a model ID would rot the same way.

Retrieval is run once and its result compared unchanged across every
generation attempt (real evidence that only generation, not retrieval,
varies with `model`), while candidate models are tried one at a time and
the first two that actually complete a real generation are kept -- a
model can be listed in the live catalog yet still fail at call time
(deprecated-but-listed, restricted access, or -- observed live during
development of this test -- a small/regional model 503ing once handed a
realistic multi-KB RAG context despite succeeding on a trivial probe
query). That in itself is real evidence for the harness this test backs:
even "configured" free models need a runtime capability check, not just
a catalog listing, before an eval run trusts them.

Requires a real, reachable stack (skipped otherwise):
- RAG_EVAL_LLM_SERVICE_URL, RAG_EVAL_VECTOR_STORE_URL,
  RAG_EVAL_INGESTION_SERVICE_URL -- base URLs for a live deployment
  (e.g. the Tailscale host: http://100.105.24.12:8003 / :8002 / :8001)
- RAG_EVAL_REPO_ID -- a repo_id already ingested on that stack
- RAG_EVAL_OLLAMA_BASE_URL (optional) -- override for the embedder when
  running from outside the stack's own Docker network, where the
  service's default OLLAMA_BASE_URL (host.docker.internal) won't resolve
  (e.g. http://100.105.24.12:11434 for the Tailscale host)
- at least two configured free-provider models that actually complete a
  real generation right now, discovered dynamically from GET /v1/models
  -- the test skips if fewer than two are available instead of failing.
"""
import asyncio
import os

import httpx
import pytest

import src.core.service as service
# service.py imports the graph-traversal helpers via the
# `rag_orchestrator.src.retrieval.*` path (not `src.retrieval.*`) --
# a separate module instance from the same file, with its own
# import-time-frozen `ingestion_service_url` global. Patch that one.
import rag_orchestrator.src.retrieval.codebase_queries as codebase_queries
import rag_orchestrator.src.retrieval.codebase_utils as codebase_utils
from src.core.config import reset_settings_cache

pytestmark = pytest.mark.integration

# provider name (as reported by GET /v1/models "providers") -> the raw
# LiteLLM-string prefix ModelRegistry.resolve() expects for that provider
# (llm_service/src/core/model_registry.py:257-270).
_RAW_MODEL_PREFIX_BY_PROVIDER = {
    "groq": "groq",
    "nvidia_nim": "nvidia_nim",
    "openrouter": "openrouter",
}

_REQUIRED_ENV_VARS = (
    "RAG_EVAL_LLM_SERVICE_URL",
    "RAG_EVAL_VECTOR_STORE_URL",
    "RAG_EVAL_INGESTION_SERVICE_URL",
    "RAG_EVAL_REPO_ID",
)

# Settings.OLLAMA_BASE_URL defaults to "http://host.docker.internal:11434",
# which only resolves from inside the stack's own Docker network -- a
# caller running this test from outside that network (e.g. this repo's
# dev machine, over Tailscale) must point it at a reachable Ollama
# instead. Optional: only the embedder needs it, and only when running
# from outside the Docker network.
_OPTIONAL_ENV_VARS = ("RAG_EVAL_OLLAMA_BASE_URL",)

_QUERY = "What does this repository do?"


def _missing_env_vars():
    return [name for name in _REQUIRED_ENV_VARS if not os.environ.get(name)]


def _iter_candidate_raw_models(catalog_response: dict):
    """Yield raw model strings for every catalog entry of every configured
    free provider -- never a fixed model ID, since that's exactly the
    fragility this test exists to catch."""
    for provider in catalog_response.get("providers", []):
        prefix = _RAW_MODEL_PREFIX_BY_PROVIDER.get(provider.get("name"))
        if not prefix or not provider.get("configured"):
            continue
        for entry in provider.get("catalog") or []:
            yield f"{prefix}/{entry['id']}"


@pytest.mark.skipif(
    bool(_missing_env_vars()),
    reason=f"live A/B harness needs env vars: {_missing_env_vars()}",
)
def test_raw_model_ab_passthrough_against_live_stack(monkeypatch):
    llm_url = os.environ["RAG_EVAL_LLM_SERVICE_URL"]
    vector_url = os.environ["RAG_EVAL_VECTOR_STORE_URL"]
    ingestion_url = os.environ["RAG_EVAL_INGESTION_SERVICE_URL"]
    repo_id = os.environ["RAG_EVAL_REPO_ID"]

    catalog_resp = httpx.get(f"{llm_url}/v1/models", timeout=30)
    catalog_resp.raise_for_status()
    catalog_response = catalog_resp.json()
    candidates = list(_iter_candidate_raw_models(catalog_response))

    monkeypatch.setenv("LLM_SERVICE_URL", llm_url)
    monkeypatch.setenv("VECTOR_STORE_URL", vector_url)
    monkeypatch.setenv("INGESTION_SERVICE_URL", ingestion_url)
    ollama_base_url = os.environ.get("RAG_EVAL_OLLAMA_BASE_URL")
    if ollama_base_url:
        monkeypatch.setenv("OLLAMA_BASE_URL", ollama_base_url)
    reset_settings_cache()
    # codebase_queries/codebase_utils read INGESTION_SERVICE_URL into a
    # module-level global at import time (not via get_settings() per
    # call), so reset_settings_cache() alone doesn't reach them -- patch
    # directly so graph traversal also hits the live host, not the
    # Docker-network-only default baked in at collection time.
    monkeypatch.setattr(codebase_queries, "ingestion_service_url", ingestion_url)
    monkeypatch.setattr(codebase_utils, "ingestion_service_url", ingestion_url)

    try:
        results = []
        skipped = []
        for raw_model in candidates:
            try:
                result = asyncio.run(
                    service.run_rag(query=_QUERY, repo_id=repo_id, model=raw_model)
                )
            except httpx.HTTPStatusError as e:
                skipped.append((raw_model, str(e)))
                continue
            if not result.answer:
                skipped.append((raw_model, "empty answer"))
                continue
            results.append((raw_model, result))
            if len(results) == 2:
                break
    finally:
        reset_settings_cache()

    if len(results) < 2:
        pytest.skip(
            "fewer than two free-provider models actually completed a "
            f"real generation right now. Tried: {candidates!r}. "
            f"Failures: {skipped!r}"
        )

    for raw_model, result in results:
        assert result.model_used == raw_model, (
            f"requested {raw_model!r} but llm_service reports "
            f"model_used={result.model_used!r} -- passthrough did not "
            "reach the provider unchanged"
        )

    (_, first_result), (_, second_result) = results
    assert (
        first_result.retrieval_plan["seed_document_ids"]
        == second_result.retrieval_plan["seed_document_ids"]
    ), (
        "retrieval must be identical across model overrides -- only "
        "generation should vary"
    )
    assert (
        first_result.retrieval_plan["expanded_document_ids"]
        == second_result.retrieval_plan["expanded_document_ids"]
    )
    assert results[0][1].model_used != results[1][1].model_used
