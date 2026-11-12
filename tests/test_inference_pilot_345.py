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
        elif self.path == "/api/chat":
            type(self).posts.append({"path": self.path, **json.loads(body)})
            self._send(
                {"done_reason": "stop", "prompt_eval_count": 9, "eval_count": 3,
                 "message": {"role": "assistant", "content": "`f`",
                             "thinking": "uses /api/embed"}}
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


def _plan_argv(tmp_path, base, plan, *extra):
    cap = tmp_path / "cap.json"
    cap.write_text(json.dumps(make_record()), encoding="utf-8")
    impl = tmp_path / "impl.txt"
    impl.write_bytes(b"line /api/embed\r\nnext")  # CRLF checkout on purpose
    plan_path = tmp_path / "plan.json"
    plan_path.write_text(json.dumps(plan), encoding="utf-8")
    return ["run", str(cap), "--api-base", base, "--out-dir", str(tmp_path / "out"),
            "--plan", str(plan_path), "--evidence", f"impl={impl}", *extra]


def test_plan_run_chat_end_to_end(tmp_path, stub, capsys):
    plan = [{"evidence": "impl", "adapter": "chat", "num_ctx": 16384, "seed": 11}]
    assert pilot.main(_plan_argv(tmp_path, stub, plan, "--authorized")) == 0
    sent = _Stub.posts[0]
    assert sent["path"] == "/api/chat"
    assert sent["messages"][1]["content"].startswith("Context:\nline /api/embed\nnext")
    rec = json.loads(
        (tmp_path / "out" / "impl-chat-ctx16384-seed11.json").read_text("utf-8")
    )
    assert rec["adapter"] == "chat"
    key = tmp_path / "key.json"
    key.write_text(
        json.dumps({"required_identifiers": ["f"], "probe_terms": ["/api/embed"]}),
        encoding="utf-8",
    )
    capsys.readouterr()
    argv = ["summarize", str(tmp_path / "out"), "--answer-key", str(key)]
    assert pilot.main(argv) == 0
    row = json.loads(capsys.readouterr().out)[0]
    assert row["adapter"] == "chat" and row["answer_chars"] == 3
    assert row["probes"]["/api/embed"] == {
        "in_context": True, "in_thinking": True, "in_answer": False
    }


def test_plan_dry_run_shows_real_fields_and_unknown_evidence_fails_cleanly(
    tmp_path, stub, capsys
):
    plan = [{"evidence": "impl", "num_ctx": 16384, "seed": 11}]
    assert pilot.main(_plan_argv(tmp_path, stub, plan, "--dry-run")) == 0
    arm = json.loads(capsys.readouterr().out)["arms"][0]
    assert arm["adapter"] == "generate" and arm["evidence"] == "impl"
    assert arm["context_bytes"] == len(b"line /api/embed\nnext")
    bad = [{"evidence": "nope", "num_ctx": 16384, "seed": 11}]
    assert pilot.main(_plan_argv(tmp_path, stub, bad, "--dry-run")) == 2
    assert _Stub.posts == []


def test_score_accepts_settings_urls_and_question_names():
    context = 'url = f"{settings.STORE_URL}/v1/search"'
    answer = "POST `/v1/rag`, then `settings.STORE_URL/v1/search`."
    s = pilot.score(answer, context, {"required_identifiers": []}, "Trace /v1/rag.")
    assert s["named_without_evidence"] == []


# Bodies LiteLLM 1.109.1 sent to a stub for system "SYS — x" and user
# "Context:\nC\n\nQuestion:\nQ" (ollama/ and ollama_chat/ routes).
LITELLM_GENERATE = (
    r'{"model": "Qwen3:4b", "prompt": "### System:\nSYS \u2014 x\n\n### User:\n'
    r'Context:\nC\n\nQuestion:\nQ\n\n", "options": {}, "stream": false, '
    r'"images": []}'
)
LITELLM_CHAT = (
    r'{"model": "Qwen3:4b", "messages": [{"role": "system", "content": '
    r'"SYS \u2014 x", "images": []}, {"role": "user", "content": '
    r'"Context:\nC\n\nQuestion:\nQ", "images": []}], "options": {}, '
    r'"stream": false}'
)


def test_builders_match_litellm_1_109_1_bytes():
    user = "Context:\nC\n\nQuestion:\nQ"
    sys_ = "SYS — x"
    gen = pilot.ollama_generate_body("Qwen3:4b", sys_, user, {})
    chat = pilot.ollama_chat_body("Qwen3:4b", sys_, user, {})
    assert gen.decode() == LITELLM_GENERATE
    assert chat.decode() == LITELLM_CHAT


def test_plan_arms_switch_adapter_and_evidence_only():
    record = make_record()
    plan = [
        {"evidence": "captured", "adapter": "generate", "num_ctx": 16384, "seed": 11},
        {"evidence": "impl", "adapter": "chat", "num_ctx": 16384, "seed": 11},
    ]
    gen, chat = pilot.plan_from_file(record, plan, {"impl": "IMPL"})
    assert gen["path"] == "/api/generate" and chat["path"] == "/api/chat"
    body = json.loads(chat["body"])
    assert body["messages"][0]["content"] == SYSTEM
    assert body["messages"][1]["content"] == f"Context:\nIMPL\n\nQuestion:\n{QUERY}"
    assert body["options"] == {"num_ctx": 16384, "seed": 11}
    captured = json.loads(record["wire"]["exchanges"][0]["request"]["body_text"])
    assert json.loads(gen["body"])["prompt"] == captured["prompt"]
    assert pilot.user_message_of(chat["body"].decode()).startswith("Context:\nIMPL")
    assert pilot.user_message_of(gen["body"].decode()).endswith(QUERY)


def test_response_parts_handles_both_routes():
    assert pilot.response_parts({"response": "a", "thinking": "t"}) == ("a", "t")
    chat = {"message": {"role": "assistant", "content": "a", "thinking": "t"}}
    assert pilot.response_parts(chat) == ("a", "t")


def test_mixed_and_factory_variant():
    assert pilot.build_mixed("D", "I", "docs-first") == "D\n\nI"
    assert pilot.build_mixed("D", "I", "impl-first") == "I\n\nD"
    names = [e[1] for e in pilot.excerpts_for("factory")]
    assert names.index("get_embedder") == names.index("embed_query") - 1
    assert len(names) == len(pilot.excerpts_for("v1")) + 1
