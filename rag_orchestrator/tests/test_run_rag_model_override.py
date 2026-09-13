# rag_orchestrator/tests/test_run_rag_model_override.py
"""
Issue TBD: direct run_rag() callers (e.g. a model-comparison eval harness)
must be able to pass an arbitrary raw LiteLLM model string straight through
to llm_service's /generate call, unchanged by any alias/slot logic in the
orchestrator layer -- the same guarantee HTTP callers already get via
RAGQuery.model.

This isolates just the LLM-call boundary in run_rag() by faking out every
retrieval-pipeline dependency it calls before reaching /generate, then
asserts on the outgoing request via httpx.MockTransport (same pattern as
test_repo_scoping.py / test_models_passthrough.py).
"""
import httpx
import pytest

import src.core.service as service

pytestmark = pytest.mark.unit


def _patch_retrieval_pipeline(monkeypatch):
    """Fake every run_rag() dependency up to (not including) the /generate
    call, so only the model passthrough is under test."""

    async def fake_resolve_repo_id_http(repo_id):
        return repo_id or "repo-x"

    monkeypatch.setattr(service, "resolve_repo_id_http", fake_resolve_repo_id_http)
    monkeypatch.setattr(service, "get_embedder", lambda **kwargs: object())
    monkeypatch.setattr(service, "embed_query", lambda query, embedder: [0.0] * 8)

    async def fake_hybrid_retrieve(*args, **kwargs):
        return {}, {
            "seed_document_ids": [],
            "expanded_document_ids": [],
            "expansion_metadata": {},
        }

    monkeypatch.setattr(service, "hybrid_retrieve", fake_hybrid_retrieve)
    monkeypatch.setattr(service, "execute_retrieval_plan", lambda **kwargs: {})
    monkeypatch.setattr(service, "prepare_chunks_for_agent", lambda *a, **k: [])
    monkeypatch.setattr(
        service, "select_chunks_within_token_budget", lambda *a, **k: []
    )
    monkeypatch.setattr(service, "build_labeled_context", lambda *a, **k: ("", 0))
    monkeypatch.setattr(service, "build_final_context_manifest", lambda *a, **k: [])
    monkeypatch.setattr(service, "build_sources", lambda *a, **k: [])


def _run_rag_capturing_generate_request(monkeypatch, **run_rag_kwargs):
    """Runs run_rag() with the retrieval pipeline faked out, capturing the
    single httpx request made to llm_service's /generate endpoint."""
    _patch_retrieval_pipeline(monkeypatch)

    captured = {}

    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/generate"
        captured["request"] = request
        return httpx.Response(
            200,
            json={
                "response": "ok",
                "model": run_rag_kwargs.get("model") or "ollama/phi4-mini:latest",
            },
        )

    real_async_client = httpx.AsyncClient

    def patched_client(*args, **kwargs):
        kwargs["transport"] = httpx.MockTransport(handler)
        return real_async_client(*args, **kwargs)

    monkeypatch.setattr(httpx, "AsyncClient", patched_client)

    import asyncio

    result = asyncio.run(service.run_rag(query="what does main do?", **run_rag_kwargs))
    return result, captured["request"]


@pytest.mark.parametrize(
    "raw_model",
    [
        "groq/openai/gpt-oss-120b",
        "openrouter/nvidia/nemotron-3-ultra-550b-a55b:free",
    ],
)
def test_run_rag_forwards_raw_model_string_unchanged(monkeypatch, raw_model):
    """A direct Python caller passing a raw provider/model string (not a
    named alias) must have it reach /generate byte-for-byte -- no
    orchestrator-side aliasing, slot lookup, or rewriting."""
    result, request = _run_rag_capturing_generate_request(
        monkeypatch, repo_id="repo-x", model=raw_model
    )

    assert request.url.params["model"] == raw_model
    assert result.model_used == raw_model


def test_run_rag_omits_model_param_when_not_given(monkeypatch):
    """Implicit-default behavior must stay unchanged: no model kwarg means
    no `model` query param at all, so llm_service falls back to its own
    default slot -- a future change must not start forcing a slot here."""
    _, request = _run_rag_capturing_generate_request(monkeypatch, repo_id="repo-x")

    assert "model" not in request.url.params


def test_run_rag_forwards_provider_alongside_model(monkeypatch):
    """provider and model are independent passthrough params -- both must
    reach /generate together, unmodified."""
    _, request = _run_rag_capturing_generate_request(
        monkeypatch,
        repo_id="repo-x",
        provider="groq",
        model="groq/openai/gpt-oss-120b",
    )

    assert request.url.params["provider"] == "groq"
    assert request.url.params["model"] == "groq/openai/gpt-oss-120b"
