"""Issue #345 pilot runner: gate, arm construction, refusal and scoring.

No real provider is contacted; a local stub stands in for Ollama.
"""

from __future__ import annotations

import hashlib
import json
import sys
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import inference_pilot_345 as pilot  # noqa: E402

SYSTEM = "You are a code-aware assistant."
CONTEXT = "[Source: a.py#f]\ndef f():\n    return g()"
QUERY = "Trace f."
DIGEST = "sha256:abc"


def make_record() -> dict:
    user = f"Context:\n{CONTEXT}\n\nQuestion:\n{QUERY}"
    body = pilot.ollama_generate_body("Qwen3:4b", SYSTEM, user, {})
    return {
        "capture_id": "cap1",
        "attempt": {"model": "ollama/Qwen3:4b", "route": "ollama"},
        "application_input": {
            "messages": [
                {"role": "system", "content": SYSTEM},
                {"role": "user", "content": user},
            ],
            "context_sha256": hashlib.sha256(CONTEXT.encode()).hexdigest(),
        },
        "wire": {
            "exchanges": [
                {
                    "request": {
                        "url": "http://provider/api/generate",
                        "body_text": body.decode(),
                        "body_sha256": hashlib.sha256(body).hexdigest(),
                    }
                }
            ]
        },
        "environment": {"ollama": {"tag": {"digest": DIGEST}}},
    }


def test_gate_passes_on_faithful_record():
    assert pilot.fidelity_gate(make_record())["passed"]


def test_gate_fails_when_body_differs():
    record = make_record()
    req = record["wire"]["exchanges"][0]["request"]
    req["body_text"] = req["body_text"].replace('"options": {}', '"options": {"x": 1}')
    gate = pilot.fidelity_gate(record)
    assert not gate["passed"] and not gate["checks"]["body_bytes_equal"]


def test_arms_change_only_options_and_context():
    record = make_record()
    arms = pilot.plan_arms(record, "IMPL", [4096, 8192], [16384], [11])
    captured = json.loads(record["wire"]["exchanges"][0]["request"]["body_text"])
    for arm in arms:
        body = json.loads(arm["body"])
        assert body["options"] == arm["options"]
        if arm["evidence"] == "captured":
            assert body["prompt"] == captured["prompt"]
        else:
            assert "Context:\nIMPL\n\nQuestion:\n" + QUERY in body["prompt"]
        assert {k: v for k, v in body.items() if k not in ("options", "prompt")} == {
            k: v for k, v in captured.items() if k not in ("options", "prompt")
        }
    assert [a["options"]["num_ctx"] for a in arms] == [4096, 8192, 16384]


def test_excerpt_whole_and_cut():
    src = "class C:\n    @d\n    def m(self):\n        a = 1\n        b = 2\n"
    assert pilot.excerpt(src, "C.m", None) == "@d\ndef m(self):\n    a = 1\n    b = 2"
    assert pilot.excerpt(src, "C.m", "a = 1") == "@d\ndef m(self):\n    a = 1"


def test_score_flags_unevidenced_names_and_admission():
    key = {"required_identifiers": ["f", "g", "h"]}
    answer = (
        "`f` calls `g` in `a.py`, then `handlers/rag_handler.py`. "
        "The context does not contain h."
    )
    s = pilot.score(answer, CONTEXT, key)
    assert s["key_present_in_context"] == 2
    assert s["key_named_of_present"] == 2
    assert s["named_without_evidence"] == ["handlers/rag_handler.py"]
    assert s["admits_insufficient"]


class _Stub(BaseHTTPRequestHandler):
    posts: list = []
    digest = DIGEST

    def _send(self, obj):
        data = json.dumps(obj).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def do_GET(self):
        if self.path == "/api/tags":
            self._send({"models": [{"name": "Qwen3:4b", "digest": self.digest}]})
        else:
            model = {"name": "Qwen3:4b", "context_length": 8192, "size_vram": 1}
            self._send({"models": [model]})

    def do_POST(self):
        body = self.rfile.read(int(self.headers["Content-Length"]))
        if self.path == "/api/generate":
            type(self).posts.append(json.loads(body))
            self._send(
                {"done_reason": "stop", "response": "`f`",
                 "prompt_eval_count": 9, "eval_count": 3}
            )
        else:
            self._send({"parameters": "temperature 0.6"})

    def log_message(self, *a):
        pass


@pytest.fixture
def stub():
    _Stub.posts = []
    _Stub.digest = DIGEST
    server = HTTPServer(("127.0.0.1", 0), _Stub)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    yield f"http://127.0.0.1:{server.server_port}"
    server.shutdown()
    server.server_close()


def _argv(tmp_path, base, *extra):
    cap = tmp_path / "cap.json"
    cap.write_text(json.dumps(make_record()), encoding="utf-8")
    return ["run", str(cap), "--api-base", base, "--out-dir", str(tmp_path / "out"),
            "--ctx", "8192", "--seed", "11", *extra]


def test_dry_run_and_unauthorized_send_nothing(tmp_path, stub):
    assert pilot.main(_argv(tmp_path, stub, "--dry-run")) == 0
    assert pilot.main(_argv(tmp_path, stub)) == 3
    assert _Stub.posts == []


def test_digest_change_aborts(tmp_path, stub):
    _Stub.digest = "sha256:other"
    assert pilot.main(_argv(tmp_path, stub, "--authorized")) == 4
    assert _Stub.posts == []


def test_authorized_run_records_and_summarizes(tmp_path, stub, capsys):
    assert pilot.main(_argv(tmp_path, stub, "--authorized")) == 0
    assert _Stub.posts[0]["options"] == {"num_ctx": 8192, "seed": 11}
    out = tmp_path / "out" / "captured-ctx8192-seed11.json"
    rec = json.loads(out.read_text(encoding="utf-8"))
    assert rec["ps_after_call"][0]["context_length"] == 8192
    key = tmp_path / "key.json"
    key.write_text(json.dumps({"required_identifiers": ["f"]}), encoding="utf-8")
    capsys.readouterr()
    argv = ["summarize", str(tmp_path / "out"), "--answer-key", str(key)]
    assert pilot.main(argv) == 0
    rows = json.loads(capsys.readouterr().out)
    assert rows[0]["done_reason"] == "stop" and rows[0]["key_named_of_present"] == 1
