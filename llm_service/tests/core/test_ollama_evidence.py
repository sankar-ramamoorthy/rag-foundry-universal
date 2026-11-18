import hashlib
import json

import httpx
import pytest
from fastapi.testclient import TestClient

from src.api.v1.main import app
from src.core import llm_client, ollama_evidence
from src.core.model_registry import ModelRegistry


@pytest.mark.parametrize("fallback", [False, True])
def test_custom_qwen_cold_and_smaller_fallback(monkeypatch, fallback):
    primary, backup = "qwen3:4b", "granite4:350m"
    windows = {primary: 8192, backup: 1024}
    digests = {primary: "a" * 64, backup: "b" * 64}
    loaded = set()
    requests = []
    passages = ["雪" * 40, "other evidence " * 100]

    def serve(req):
        data = json.loads(req.content) if req.content else {}
        model = data.get("model")
        if req.url.path == "/api/version":
            payload = {"version": "0.32.1"}
        elif req.url.path == "/api/ps":
            payload = {
                "models": [
                    {"name": m, "context_length": windows[m], "digest": digests[m]}
                    for m in loaded
                ]
            }
        elif req.url.path == "/api/show":
            payload = {
                "model_info": {
                    "tokenizer.ggml.model": "gpt2",
                    "tokenizer.ggml.pre": "qwen2" if model == primary else "dbrx",
                }
            }
        elif data.get("_debug_render_only"):
            prompt = (
                data["prompt"]
                if "template" in data
                else "host template " + data["prompt"]
            )
            payload = {"done": False, "_debug_info": {"rendered_template": prompt}}
        elif "prompt" not in data:
            loaded.add(model)
            payload = {"done": True}
        else:
            requests.append(data)
            if model == primary and fallback:
                return httpx.Response(503)
            payload = {
                "model": model,
                "done": True,
                "prompt_eval_count": 200,
                "eval_count": 4,
                "response": "answer",
            }
        return httpx.Response(200, json=payload)

    real_client = httpx.AsyncClient
    monkeypatch.setattr(
        ollama_evidence,
        "_client",
        lambda **kw: real_client(transport=httpx.MockTransport(serve), **kw),
    )
    registry = ModelRegistry(
        {
            "models": {"main": "ollama/" + primary, "backup": "ollama/" + backup},
            "fallbacks": {"main": ["backup"]},
        }
    )
    monkeypatch.setattr(llm_client, "get_registry", lambda: registry)
    monkeypatch.setattr(ollama_evidence, "RETRY_BACKOFF_BASE_SECONDS", 0)
    response = TestClient(app).post(
        "/generate?model=main",
        json={
            "query": "Question?",
            "context": "\n\n".join(passages),
            "evidence_passages": passages,
        },
        headers={"X-RAG-Capacity": "enlarged", "X-RAG-Output-Reserve": "128"},
    )
    assert response.status_code == 200, response.text
    receipt = response.json()["capacity"]
    count = 1 if fallback else 2
    wire = requests[-1]
    assert wire["model"] == (backup if fallback else primary)
    assert wire["truncate"] is False and wire["shift"] is False
    assert wire["prompt"].startswith("host template ")
    assert receipt["prompt_bytes"] == len(wire["prompt"].encode())
    assert receipt["prompt_token_upper_bound"] + 128 <= windows[wire["model"]]
    assert wire["options"] == {"num_ctx": windows[wire["model"]], "num_predict": 128}
    assert receipt["delivered_passage_count"] == count
    delivered = "\n\n".join(passages[:count])
    assert delivered in wire["prompt"]
    assert ("other evidence" in wire["prompt"]) == (not fallback)
    assert (
        receipt["delivered_evidence_sha256"]
        == hashlib.sha256(delivered.encode()).hexdigest()
    )


@pytest.mark.parametrize(
    "failure",
    [
        "unverified_version",
        "missing_user",
        "changed_final_render",
        "invalid_ps",
        "unknown_tokenizer",
        "runner_changed",
        "usage_exceeds_estimate",
        "no_passage_fits",
    ],
)
def test_custom_admission_fails_closed(monkeypatch, failure):
    model = "qwen3:4b"
    sent = []
    real_client = httpx.AsyncClient
    monkeypatch.setattr(ollama_evidence, "_verified_until", {})

    def serve(req):
        data = json.loads(req.content) if req.content else {}
        if req.url.path == "/api/version":
            payload = {
                "version": "0.7" if failure == "unverified_version" else "0.32.1"
            }
        elif req.url.path == "/api/ps":
            digest = "b" if failure == "runner_changed" and sent else "a"
            payload = {
                "models": [
                    {
                        "name": model,
                        "digest": digest * 64,
                        "context_length": None if failure == "invalid_ps" else 1024,
                    }
                ]
            }
        elif req.url.path == "/api/show":
            payload = {
                "model_info": {
                    "tokenizer.ggml.model": "unknown"
                    if failure == "unknown_tokenizer"
                    else "gpt2",
                    "tokenizer.ggml.pre": "qwen2",
                }
            }
        elif data.get("_debug_render_only"):
            rendered = data["prompt"]
            if failure == "missing_user":
                rendered = "model template omits input"
            if failure == "changed_final_render" and "template" in data:
                rendered += " changed"
            payload = {"done": False, "_debug_info": {"rendered_template": rendered}}
        else:
            sent.append(data)
            payload = {
                "model": model,
                "done": True,
                "response": "answer",
                "prompt_eval_count": 1025
                if failure == "usage_exceeds_estimate"
                else 12,
                "eval_count": 2,
            }
        return httpx.Response(200, json=payload)

    monkeypatch.setattr(
        ollama_evidence,
        "_client",
        lambda **kw: real_client(transport=httpx.MockTransport(serve), **kw),
    )
    source = "x" * (2000 if failure == "no_passage_fits" else 10)
    response = TestClient(app).post(
        "/generate?model=ollama/qwen3:4b",
        json={
            "query": "Why?",
            "context": source,
            "evidence_passages": [source],
        },
        headers={"X-RAG-Capacity": "enlarged", "X-RAG-Output-Reserve": "128"},
    )
    assert response.status_code == 413, response.text
    assert bool(sent) == (failure in {"runner_changed", "usage_exceeds_estimate"})


def test_context_must_match_evidence_manifest():
    response = TestClient(app).post(
        "/generate",
        json={
            "query": "Why?",
            "context": "different",
            "evidence_passages": ["evidence"],
        },
    )
    assert response.status_code == 422
