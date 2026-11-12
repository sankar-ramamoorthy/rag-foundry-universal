"""Replay a captured provider-bound LLM request (issue #344).

Reads one ``llm_provider_capture.v1`` record written by llm_service when
LLM_PROVIDER_CAPTURE_DIR is set, re-sends the captured wire request to the
provider, and writes an ``llm_provider_replay.v1`` record next to it.

Without overrides the request bytes are sent exactly as captured. Any
override (``--api-base``, ``--set-option``) is listed in the replay record,
and the body is then re-serialized, so ``body_identical`` becomes false.
The replay record also lists environment differences: Ollama version,
model digest, Modelfile parameters, template hash and loaded context
length, captured versus now.

This sends a real inference request (it uses GPU/CPU on the provider), so
run it deliberately. It is diagnostic tooling, not part of any service.

    python scripts/replay_llm_capture.py CAPTURE.json \
        [--api-base http://host:11434] [--set-option num_ctx=16384] [--out PATH]
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit, urlunsplit

import httpx

SCHEMA = "llm_provider_replay.v1"
_ENV_FIELDS = (
    ("version",),
    ("tag", "digest"),
    ("show", "parameters"),
    ("show", "template_sha256"),
    ("ps_after_call", 0, "context_length"),
)


def sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def parse_option(text: str) -> tuple[str, Any]:
    """``key=value`` with a JSON value when it parses (numbers, bools),
    otherwise the raw string."""
    key, sep, raw = text.partition("=")
    if not sep or not key:
        raise argparse.ArgumentTypeError(f"expected key=value, got {text!r}")
    try:
        return key, json.loads(raw)
    except ValueError:
        return key, raw


def rebase_url(url: str, api_base: str | None) -> str:
    if not api_base:
        return url
    original, base = urlsplit(url), urlsplit(api_base)
    return urlunsplit((base.scheme, base.netloc, original.path, original.query, ""))


def build_request(
    record: dict, options: list[tuple[str, Any]], api_base: str | None
) -> dict:
    """The request to send, plus what was changed relative to the capture."""
    wire = record.get("wire") or {}
    exchanges = wire.get("exchanges") or []
    if not exchanges or not (exchanges[-1].get("request") or {}).get("body_text"):
        raise ValueError(
            "capture has no wire request body (non-Ollama route or omitted for "
            "size); replay needs the exact captured bytes"
        )
    captured = exchanges[-1]["request"]
    body_bytes = captured["body_text"].encode("utf-8")
    overrides: list[dict] = []
    if options:
        body = json.loads(body_bytes)
        body.setdefault("options", {})
        for key, value in options:
            overrides.append(
                {
                    "field": f"options.{key}",
                    "from": body["options"].get(key),
                    "to": value,
                }
            )
            body["options"][key] = value
        body_bytes = json.dumps(body).encode("utf-8")
    url = rebase_url(captured["url"], api_base)
    if url != captured["url"]:
        overrides.append({"field": "api_base", "from": "captured", "to": "override"})
    return {
        "url": url,
        "body_bytes": body_bytes,
        "body_identical": body_bytes == captured["body_text"].encode("utf-8"),
        "captured_body_sha256": captured.get("body_sha256"),
        "overrides": overrides,
    }


def _get(obj: Any, path: tuple) -> Any:
    for key in path:
        try:
            obj = obj[key]
        except (KeyError, IndexError, TypeError):
            return None
    return obj


def environment_diff(before: dict | None, after: dict | None) -> list[dict]:
    diffs = []
    for path in _ENV_FIELDS:
        old, new = _get(before or {}, path), _get(after or {}, path)
        if old != new:
            diffs.append(
                {"field": ".".join(map(str, path)), "captured": old, "now": new}
            )
    return diffs


def ollama_environment(client: httpx.Client, api_base: str, model: str) -> dict:
    env: dict = {}
    try:
        env["version"] = client.get(f"{api_base}/api/version").json().get("version")
        tags = client.get(f"{api_base}/api/tags").json().get("models", [])
        match = [m for m in tags if model in (m.get("name"), m.get("model"))]
        if match:
            env["tag"] = {"digest": match[0].get("digest")}
        show = client.post(f"{api_base}/api/show", json={"model": model}).json()
        template = (show.get("template") or "").encode("utf-8")
        env["show"] = {
            "parameters": show.get("parameters"),
            "template_sha256": sha256(template) if template else None,
        }
        models = client.get(f"{api_base}/api/ps").json().get("models", [])
        env["ps_after_call"] = [
            {k: m.get(k) for k in ("name", "context_length", "size_vram")}
            for m in models
            if model in (m.get("name"), m.get("model"))
        ]
    except Exception as e:  # noqa: BLE001 - environment is best-effort
        env["error"] = str(e)
    return env


def replay(
    record: dict,
    options: list[tuple[str, Any]],
    api_base: str | None,
    timeout: float = 600,
) -> dict:
    request = build_request(record, options, api_base)
    parts = urlsplit(request["url"])
    base = urlunsplit((parts.scheme, parts.netloc, "", "", ""))
    model = record["attempt"]["model"].split("/", 1)[-1]
    started = datetime.now(timezone.utc)
    with httpx.Client(timeout=timeout) as client:
        response = client.post(
            request["url"],
            content=request["body_bytes"],
            headers={"Content-Type": "application/json"},
        )
        raw = response.content
        env_now = ollama_environment(client, base, model)
    try:
        body_json = json.loads(raw)
    except ValueError:
        body_json = None
    captured_env = (record.get("environment") or {}).get("ollama")
    return {
        "schema": SCHEMA,
        "replayed_at": started.isoformat(),
        "source_capture_id": record.get("capture_id"),
        "trace_id": record.get("trace_id"),
        "model": record["attempt"]["model"],
        "request": {
            "body_identical": request["body_identical"],
            "body_sha256": sha256(request["body_bytes"]),
            "captured_body_sha256": request["captured_body_sha256"],
            "overrides": request["overrides"],
        },
        "response": {
            "status_code": response.status_code,
            "body_text": raw.decode("utf-8", errors="replace"),
            "body_json": body_json,
        },
        "environment_now": env_now,
        "environment_diff": environment_diff(captured_env, env_now),
    }


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description=(__doc__ or "").split("\n\n")[0])
    parser.add_argument("capture", type=Path)
    parser.add_argument("--api-base", help="send to this base URL instead")
    parser.add_argument(
        "--set-option",
        action="append",
        type=parse_option,
        default=[],
        metavar="KEY=VALUE",
        help="override one provider option (repeatable)",
    )
    parser.add_argument("--out", type=Path, help="replay record path")
    parser.add_argument("--timeout", type=float, default=600)
    args = parser.parse_args(argv)

    record = json.loads(args.capture.read_text(encoding="utf-8"))
    result = replay(record, args.set_option, args.api_base, args.timeout)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    out = args.out or args.capture.with_name(f"{args.capture.stem}.replay-{stamp}.json")
    # Owner-only, never overwrite: replay output is as sensitive as the capture.
    try:
        fd = os.open(out, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    except FileExistsError:
        raise SystemExit(f"refusing to overwrite {out}") from None
    with os.fdopen(fd, "w", encoding="utf-8") as handle:
        handle.write(json.dumps(result, ensure_ascii=False, indent=1))
    print(
        json.dumps(
            {
                "out": str(out),
                "status": result["response"]["status_code"],
                "body_identical": result["request"]["body_identical"],
                "overrides": result["request"]["overrides"],
                "environment_diff": result["environment_diff"],
            },
            indent=1,
        )
    )


if __name__ == "__main__":
    main()
