# llm_service/tests/core/test_provider_capture.py
"""
Issue #344: opt-in capture of the exact provider-bound request.

A local stub Ollama server records the bytes it actually receives, so
fidelity is checked against the wire, not against our own bookkeeping.
No real model is called.
"""

import json
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

import src.core.llm_client as llm_client
from src.core import provider_capture
from src.core.model_registry import ResolvedModel

SECRET = "sk-test-secret-value"


_MODEL = {"name": "Qwen3:4b", "model": "Qwen3:4b"}
_GET_ROUTES = {
    "/api/version": {"version": "0.0.test"},
    "/api/tags": {"models": [{**_MODEL, "digest": "abc123", "size": 1}]},
    "/api/ps": {"models": [{**_MODEL, "context_length": 4096, "size_vram": 99}]},
}
_POST_ROUTES = {
    "/api/show": {
        "parameters": "temperature 0.6",
        "template": "{{ .Prompt }}",
        "details": {"family": "qwen3"},
        "capabilities": ["thinking"],
        "model_info": {"qwen3.context_length": 262144},
    },
    # /api/generate: LiteLLM drops thinking/done_reason; only the wire keeps them
    "/api/generate": {
        "model": "Qwen3:4b",
        "response": "ANSWER",
        "thinking": "THOUGHTS",
        "done": True,
        "done_reason": "length",
        "prompt_eval_count": 11,
        "eval_count": 7,
    },
    "/api/chat": {
        "model": "Qwen3:4b",
        "message": {"role": "assistant", "content": "ANSWER"},
        "done": True,
        "done_reason": "stop",
        "prompt_eval_count": 11,
        "eval_count": 7,
    },
}
_INFERENCE = ("/api/generate", "/api/chat")


class _Stub:
    """Local stand-in for Ollama that records the exact bytes received."""

    def __init__(self):
        self.received = []  # (path, headers, raw bytes)
        self.fail_inference = False
        stub = self

        class Handler(BaseHTTPRequestHandler):
            def _send(self, status, payload):
                body = json.dumps(payload).encode()
                self.send_response(status)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)

            def do_GET(self):
                payload = _GET_ROUTES.get(self.path)
                self._send(200 if payload else 404, payload or {})

            def do_POST(self):
                raw = self.rfile.read(int(self.headers["Content-Length"]))
                stub.received.append((self.path, dict(self.headers), raw))
                if stub.fail_inference and self.path in _INFERENCE:
                    self._send(500, {"error": "boom"})
                    return
                payload = _POST_ROUTES.get(self.path)
                self._send(200 if payload else 404, payload or {})

            def log_message(self, *args):
                pass

        self.server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        self.base = f"http://127.0.0.1:{self.server.server_address[1]}"
        threading.Thread(target=self.server.serve_forever, daemon=True).start()

    def inference(self):
        return [r for r in self.received if r[0] in _INFERENCE]


@pytest.fixture()
def stub():
    s = _Stub()
    yield s
    s.server.shutdown()


@pytest.fixture()
def capture_dir(tmp_path, monkeypatch):
    monkeypatch.setenv("LLM_PROVIDER_CAPTURE_DIR", str(tmp_path))
    monkeypatch.setattr(llm_client, "RETRY_BACKOFF_BASE_SECONDS", 0)
    provider_capture.set_request_meta()
    return tmp_path


def _records(directory: Path):
    return [
        json.loads(p.read_text(encoding="utf-8"))
        for p in sorted(directory.rglob("*.json"))
    ]


def _resolved(stub, model):
    return ResolvedModel(alias="remote", model=model, api_base=stub.base, timeout=10)


async def test_disabled_by_default_changes_nothing(monkeypatch, tmp_path):
    monkeypatch.delenv("LLM_PROVIDER_CAPTURE_DIR", raising=False)
    calls = {}

    class _Resp:
        class _C:
            class message:
                content = "x"

        choices = [_C()]
        usage = None

    async def fake_acompletion(**kwargs):
        calls.update(kwargs)
        return _Resp()

    monkeypatch.setattr(llm_client.litellm, "acompletion", fake_acompletion)
    await llm_client._complete(
        ResolvedModel(alias=None, model="ollama/m", api_base="http://x", timeout=1),
        context="secret source",
        query="q",
    )
    assert "client" not in calls
    assert not list(tmp_path.rglob("*.json"))


@pytest.mark.parametrize(
    "route,path", [("ollama", "/api/generate"), ("ollama_chat", "/api/chat")]
)
async def test_wire_bytes_match_capture(stub, capture_dir, route, path):
    provider_capture.set_request_meta(
        trace_id="trace-1", repo_id="repo-1", generation_id="gen-1"
    )
    result = await llm_client._complete(
        _resolved(stub, f"{route}/Qwen3:4b"), context="EVIDENCE", query="Q?"
    )
    assert result["response"] == "ANSWER"

    [record] = _records(capture_dir)
    [(received_path, _, received_bytes)] = stub.inference()
    assert received_path == path

    [exchange] = record["wire"]["exchanges"]
    # Fidelity: the bytes the server received are exactly the captured bytes,
    # and parse to the body LiteLLM reported in its pre-call hook.
    assert exchange["request"]["body_text"].encode("utf-8") == received_bytes
    assert json.loads(received_bytes) == record["provider_request"]["body"]
    assert record["provider_request"]["url"].endswith(path)

    body = record["provider_request"]["body"]
    assert body["options"] == {}  # provider defaults: recorded, not invented
    if route == "ollama":
        assert body["prompt"].startswith("### System:\n")
        assert "### User:\nContext:\nEVIDENCE" in body["prompt"]
        # LiteLLM drops these from its response object; only the wire keeps them.
        assert exchange["response"]["body_json"]["thinking"] == "THOUGHTS"
        assert exchange["response"]["body_json"]["done_reason"] == "length"
    else:
        assert [m["role"] for m in body["messages"]] == ["system", "user"]

    assert [m["role"] for m in record["application_input"]["messages"]] == [
        "system",
        "user",
    ]
    assert (record["trace_id"], record["repo_id"], record["generation_id"]) == (
        "trace-1",
        "repo-1",
        "gen-1",
    )
    assert record["result"]["status"] == "ok"
    assert record["result"]["usage"]["prompt_tokens"] == 11
    ollama = record["environment"]["ollama"]
    assert ollama["version"] == "0.0.test"
    assert ollama["tag"]["digest"] == "abc123"
    assert ollama["show"]["parameters"] == "temperature 0.6"
    assert ollama["ps_after_call"][0]["context_length"] == 4096
    assert record["environment"]["litellm_version"]


async def test_provider_failure_is_captured_and_still_raises(stub, capture_dir):
    stub.fail_inference = True
    with pytest.raises(Exception):
        await llm_client._complete(
            _resolved(stub, "ollama/Qwen3:4b"), context="c", query="q"
        )

    [record] = _records(capture_dir)
    assert record["result"]["status"] == "error"
    # one exchange per transient retry, each with the 500 response
    exchanges = record["wire"]["exchanges"]
    assert len(exchanges) == llm_client.MAX_TRANSIENT_RETRIES + 1
    assert all(e["response"]["status_code"] == 500 for e in exchanges)


async def test_credentials_are_redacted(stub, capture_dir, monkeypatch):
    monkeypatch.setenv("OLLAMA_API_KEY", SECRET)
    await llm_client._complete(
        _resolved(stub, "ollama_chat/Qwen3:4b"), context="c", query="q"
    )

    [(_, headers, _)] = stub.inference()
    sent_auth = {k.lower(): v for k, v in headers.items()}.get("authorization", "")
    text = "".join(p.read_text(encoding="utf-8") for p in capture_dir.rglob("*.json"))
    assert SECRET in sent_auth  # the key really went over the wire...
    assert SECRET not in text  # ...and never reaches the capture record
    assert "<redacted>" in text
    assert provider_capture.redact_headers(
        {"Authorization": "Bearer x", "X-Api-Key": "y", "A": "b"}
    ) == {"Authorization": "<redacted>", "X-Api-Key": "<redacted>", "A": "b"}


async def test_size_limit_omits_bodies_explicitly(stub, capture_dir, monkeypatch):
    monkeypatch.setenv("LLM_PROVIDER_CAPTURE_MAX_BYTES", "2000")
    await llm_client._complete(
        _resolved(stub, "ollama/Qwen3:4b"), context="E" * 5000, query="q"
    )

    [record] = _records(capture_dir)
    assert record["provider_request"]["body"] is None
    assert record["application_input"]["messages"] is None
    omitted = record["omitted"]
    assert "provider_request.body_sha256" in omitted
    assert "wire.exchanges[0].request.body_sha256" in omitted
    assert record["application_input"]["context_bytes"] == 5000


async def test_capture_write_failure_never_fails_generation(
    stub, capture_dir, monkeypatch
):
    def boom(record):
        raise OSError("disk full")

    monkeypatch.setattr(provider_capture, "_write_record", boom)
    result = await llm_client._complete(
        _resolved(stub, "ollama/Qwen3:4b"), context="c", query="q"
    )
    assert result["response"] == "ANSWER"


def test_generate_endpoint_records_correlation_headers(stub, capture_dir, monkeypatch):
    from src.api.v1.main import app

    class _Registry:
        def resolve(self, provider, model):
            return _resolved(stub, "ollama_chat/Qwen3:4b")

        def fallback_chain(self, primary):
            return [primary]

    monkeypatch.setattr(llm_client, "get_registry", lambda: _Registry())
    response = TestClient(app).post(
        "/generate",
        json={"context": "c", "query": "q"},
        headers={"X-Trace-Id": "t-42", "X-Repo-Id": "r-1", "X-Generation-Id": "g-9"},
    )
    assert response.status_code == 200
    # capture never adds prompt/body data to the public response
    assert not {"context", "messages", "prompt", "capture"} & set(response.json())

    [record] = _records(capture_dir)
    assert (record["trace_id"], record["repo_id"], record["generation_id"]) == (
        "t-42",
        "r-1",
        "g-9",
    )
