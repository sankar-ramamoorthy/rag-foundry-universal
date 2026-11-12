"""Replay of a captured provider request (#344) against a local stub; no model."""

import importlib.util
import json
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import pytest

SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "replay_llm_capture.py"
SPEC = importlib.util.spec_from_file_location("replay_llm_capture", SCRIPT)
assert SPEC is not None and SPEC.loader is not None
replay = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(replay)

pytestmark = pytest.mark.unit

# Deliberately not json.dumps output: replay must send these exact bytes.
CAPTURED_BODY = (
    '{"model": "Qwen3:4b", "prompt": "### System:\\nS\\n\\n", "options": {}}'
)
GET_ROUTES = {
    "/api/version": {"version": "0.0.new"},
    "/api/tags": {"models": [{"name": "Qwen3:4b", "digest": "abc"}]},
    "/api/ps": {"models": [{"name": "Qwen3:4b", "context_length": 16384}]},
}


@pytest.fixture()
def stub():
    received = []

    class Handler(BaseHTTPRequestHandler):
        def _send(self, payload):
            body = json.dumps(payload).encode()
            self.send_response(200)
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def do_GET(self):
            self._send(GET_ROUTES.get(self.path, {}))

        def do_POST(self):
            raw = self.rfile.read(int(self.headers["Content-Length"]))
            if self.path == "/api/show":
                self._send({"parameters": "temperature 0.6", "template": "T"})
                return
            received.append((self.path, raw))
            self._send({"response": "ANSWER", "done_reason": "stop"})

        def log_message(self, *args):
            pass

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    yield f"http://127.0.0.1:{server.server_address[1]}", received
    server.shutdown()
    server.server_close()


def _record(base: str) -> dict:
    return {
        "capture_id": "cap-1",
        "trace_id": "t-1",
        "attempt": {"model": "ollama/Qwen3:4b"},
        "wire": {
            "exchanges": [
                {
                    "request": {
                        "url": f"{base}/api/generate",
                        "body_text": CAPTURED_BODY,
                        "body_sha256": "x",
                    }
                }
            ]
        },
        "environment": {
            "ollama": {
                "version": "0.0.old",
                "tag": {"digest": "abc"},
                "ps_after_call": [{"context_length": 4096}],
            }
        },
    }


def test_replay_sends_the_captured_bytes_unchanged(stub):
    base, received = stub
    result = replay.replay(_record(base), [], None)

    assert received == [("/api/generate", CAPTURED_BODY.encode())]
    assert result["request"]["body_identical"] is True
    assert result["request"]["overrides"] == []
    assert result["response"]["body_json"]["response"] == "ANSWER"
    diffs = {d["field"]: d for d in result["environment_diff"]}
    assert diffs["version"]["captured"] == "0.0.old"
    assert diffs["ps_after_call.0.context_length"]["now"] == 16384
    assert "tag.digest" not in diffs


def test_option_override_is_explicit(stub):
    base, received = stub
    option = replay.parse_option("num_ctx=16384")
    result = replay.replay(_record(base), [option], None)

    sent = json.loads(received[0][1])
    assert sent["options"] == {"num_ctx": 16384}
    assert result["request"]["body_identical"] is False
    assert result["request"]["overrides"] == [
        {"field": "options.num_ctx", "from": None, "to": 16384}
    ]


def test_capture_without_wire_bytes_is_refused():
    record = {"attempt": {"model": "openai/gpt"}, "wire": None}
    with pytest.raises(ValueError, match="no wire request body"):
        replay.build_request(record, [], None)


def test_api_base_override_keeps_path():
    assert (
        replay.rebase_url("http://a:1/api/chat?x=1", "http://b:2")
        == "http://b:2/api/chat?x=1"
    )
