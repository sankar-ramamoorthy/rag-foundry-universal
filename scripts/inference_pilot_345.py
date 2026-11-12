"""Issue #345 pilot: context allocation and evidence, provider requests only.

Sends seeded, controlled variants of the Step 0 capture's provider request
directly to Ollama. Production configuration is never touched: the deployed
services are not called, and only the request body sent here differs.

Arms vary exactly one thing at a time:

- ``captured`` evidence: the Step 0 context and question, byte-identical
  prompt, with ``options`` set to ``{num_ctx, seed}``.
- ``implementation`` evidence: the same question and system prompt with a
  reviewed context of real implementation excerpts (``build-context``).

Before anything is sent, a fidelity gate rebuilds the Step 0 wire body from
the record's ``application_input.messages`` (LiteLLM ``ollama/`` flattening)
and requires it to match the captured bytes and sha256, and requires the
model digest on the server to equal Step 0's.

This uses the provider's GPU. ``run`` refuses without ``--authorized`` and
``--dry-run`` sends nothing (it does read-only ``/api/tags`` and
``/api/show`` checks only when ``--api-base`` is given).

    python scripts/inference_pilot_345.py build-context --out CONTEXT.txt
    python scripts/inference_pilot_345.py run CAPTURE.json --api-base URL \
        --impl-context CONTEXT.txt --answer-key KEY.json --out-dir DIR \
        [--dry-run | --authorized]
    python scripts/inference_pilot_345.py summarize DIR --answer-key KEY.json
"""

from __future__ import annotations

import argparse
import ast
import hashlib
import json
import os
import re
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import httpx

SCHEMA = "inference_pilot_345.v1"
INGESTED_COMMIT = "8e06335"

# Reviewed implementation excerpts for the Step 0 question (POST /v1/rag ->
# orchestrator -> vector retrieval), at the commit the self-repo was ingested
# from. (path, symbol, end_marker): the whole definition when end_marker is
# None, otherwise the definition from its first line through the first line
# containing end_marker (the part of a long function that reaches vector
# retrieval). Order follows the call sequence.
IMPLEMENTATION_EXCERPTS: list[tuple[str, str, str | None]] = [
    ("rag_orchestrator/src/api/v1/routes.py", "rag_endpoint", None),
    ("rag_orchestrator/src/core/service.py", "run_rag", "trace_id=trace_id,\n    )"),
    ("rag_orchestrator/src/core/service.py", "resolve_repo_id_http", None),
    ("shared/embedders/query.py", "embed_query", None),
    ("shared/embedders/ollama.py", "OllamaEmbedder.embed", None),
    (
        "rag_orchestrator/src/core/service.py",
        "hybrid_retrieve",
        'raw_results = resp.json().get("results", [])',
    ),
    ("rag_orchestrator/src/core/service.py", "_query_generation", None),
    ("vector_store_service/src/api/v1/vectors.py", "similarity_search", None),
    (
        "vector_store_service/src/core/vectorstore/pgvector_store.py",
        "PgVectorStore.similarity_search",
        None,
    ),
]

ADMISSION_RE = re.compile(
    r"(does not|doesn't|do not) (contain|include|provide|show)|"
    r"cannot (trace|determine|answer|identify|give|provide)|"
    r"not (provided|included|present|available) in the (provided )?context|"
    r"insufficient",
    re.IGNORECASE,
)


def sha256(data: bytes | str) -> str:
    if isinstance(data, str):
        data = data.encode("utf-8")
    return hashlib.sha256(data).hexdigest()


# ---------------------------------------------------------------- context


def _find_def(tree: ast.Module, dotted: str) -> ast.AST:
    scope: Any = tree
    for part in dotted.split("."):
        for node in scope.body:
            if (
                isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef))
                and node.name == part
            ):
                scope = node
                break
        else:
            raise LookupError(f"{dotted}: {part} not found")
    return scope


def excerpt(source: str, symbol: str, end_marker: str | None) -> str:
    node = _find_def(ast.parse(source), symbol)
    start = min([node.lineno] + [d.lineno for d in node.decorator_list])  # type: ignore[attr-defined]
    lines = source.splitlines()
    text = "\n".join(lines[start - 1 : node.end_lineno])  # type: ignore[attr-defined]
    if end_marker is not None:
        cut = text.find(end_marker)
        if cut < 0:
            raise LookupError(f"{symbol}: end marker not found")
        text = text[: cut + len(end_marker)]
    # Drop the definition's own indentation (methods) so excerpts read alike.
    indent = len(text) - len(text.lstrip(" "))
    return "\n".join(line[indent:] if line[:indent].isspace() else line
                     for line in text.splitlines())


def build_context(
    commit: str = INGESTED_COMMIT,
    excerpts: list[tuple[str, str, str | None]] = IMPLEMENTATION_EXCERPTS,
    show=None,
) -> str:
    """Orchestrator-style ``[Source: label]`` blocks joined by blank lines."""
    show = show or (
        lambda c, p: subprocess.run(
            ["git", "show", f"{c}:{p}"], check=True, capture_output=True
        ).stdout.decode("utf-8")
    )
    blocks = []
    for path, symbol, end_marker in excerpts:
        text = excerpt(show(commit, path), symbol, end_marker)
        blocks.append(f"[Source: {path}#{symbol}]\n{text}")
    return "\n\n".join(blocks)


# ---------------------------------------------------------------- requests


def split_user_message(content: str) -> tuple[str, str]:
    """Inverse of rag_answer.v1's user message."""
    head, sep, query = content.rpartition("\n\nQuestion:\n")
    if not sep or not head.startswith("Context:\n"):
        raise ValueError("user message is not rag_answer.v1-shaped")
    return head[len("Context:\n") :], query


def ollama_generate_body(
    model: str, system: str, user: str, options: dict
) -> bytes:
    """The /api/generate body LiteLLM's ``ollama/`` route builds (1.109.1):
    roles flattened into one prompt, default json.dumps separators."""
    prompt = f"### System:\n{system}\n\n### User:\n{user}\n\n"
    body = {
        "model": model,
        "prompt": prompt,
        "options": options,
        "stream": False,
        "images": [],
    }
    return json.dumps(body).encode("utf-8")


def fidelity_gate(record: dict) -> dict:
    """Rebuild the captured wire body from the record's messages; every
    arm is built by the same function, so a match means arms differ from
    production only in what they deliberately change."""
    request = record["wire"]["exchanges"][-1]["request"]
    captured = request["body_text"].encode("utf-8")
    messages = record["application_input"]["messages"]
    system, user = messages[0]["content"], messages[1]["content"]
    model = json.loads(captured)["model"]
    rebuilt = ollama_generate_body(model, system, user, {})
    context, _query = split_user_message(user)
    checks = {
        "body_bytes_equal": rebuilt == captured,
        "body_sha256_equal": sha256(rebuilt) == request.get("body_sha256"),
        "context_sha256_equal": sha256(context)
        == record["application_input"].get("context_sha256"),
        "route_is_ollama_generate": record["attempt"]["route"] == "ollama"
        and request["url"].endswith("/api/generate"),
    }
    return {"passed": all(checks.values()), "checks": checks, "model": model}


def plan_arms(
    record: dict,
    impl_context: str | None,
    ctx_sizes: list[int],
    impl_ctx_sizes: list[int],
    seeds: list[int],
) -> list[dict]:
    messages = record["application_input"]["messages"]
    system, user = messages[0]["content"], messages[1]["content"]
    captured_context, query = split_user_message(user)
    model = json.loads(record["wire"]["exchanges"][-1]["request"]["body_text"])[
        "model"
    ]
    evidence = {"captured": captured_context}
    if impl_context is not None:
        evidence["implementation"] = impl_context
    arms = []
    for name, context in evidence.items():
        sizes = ctx_sizes if name == "captured" else impl_ctx_sizes
        user_msg = f"Context:\n{context}\n\nQuestion:\n{query}"
        for num_ctx in sizes:
            for seed in seeds:
                options = {"num_ctx": num_ctx, "seed": seed}
                arms.append(
                    {
                        "arm_id": f"{name}-ctx{num_ctx}-seed{seed}",
                        "evidence": name,
                        "context_bytes": len(context.encode("utf-8")),
                        "context_sha256": sha256(context),
                        "options": options,
                        "body": ollama_generate_body(model, system, user_msg, options),
                    }
                )
    # Group by num_ctx so Ollama reloads the model as rarely as possible.
    arms.sort(
        key=lambda a: (a["options"]["num_ctx"], a["evidence"], a["options"]["seed"])
    )
    return arms


# ---------------------------------------------------------------- scoring


_BACKTICK = re.compile(r"`([^`\s]+)`")
_PY_PATH = re.compile(r"\b[\w./-]+\.py\b")


def named_identifiers(answer: str) -> set[str]:
    names = set(_PY_PATH.findall(answer))
    for token in _BACKTICK.findall(answer):
        token = token.strip()
        if re.fullmatch(r"[\w./{}:-]+(\(\))?", token):
            names.add(token.removesuffix("()"))
    return names


def _evidenced(name: str, context: str) -> bool:
    """A file path counts if its basename appears in the context; a dotted
    identifier if its last component does."""
    if name in context:
        return True
    if "/" in name and not name.endswith(".py"):
        # URL built from a settings variable: the path part must appear.
        return name[name.find("/") :] in context
    if name.endswith(".py"):
        return name.rsplit("/", 1)[-1] in context
    return name.rsplit(".", 1)[-1] in context


def score(answer: str, context: str, key: dict, query: str = "") -> dict:
    """Names from the question count as given, not invented."""
    named = named_identifiers(answer)
    given = f"{context}\n{query}"
    required = key["required_identifiers"]
    present = [k for k in required if k in context]
    return {
        "key_present_in_context": len(present),
        "key_named_of_present": sum(1 for k in present if k in answer),
        "key_named_total": sum(1 for k in required if k in answer),
        "key_missing_from_answer": [k for k in required if k not in answer],
        "named_without_evidence": sorted(
            n for n in named if not _evidenced(n, given)
        ),
        "admits_insufficient": bool(ADMISSION_RE.search(answer)),
    }


# ---------------------------------------------------------------- running


def server_state(client: httpx.Client, api_base: str, model: str) -> dict:
    tags = client.get(f"{api_base}/api/tags").json().get("models", [])
    digest = next(
        (m.get("digest") for m in tags if model in (m.get("name"), m.get("model"))),
        None,
    )
    show = client.post(f"{api_base}/api/show", json={"model": model}).json()
    return {"digest": digest, "parameters": show.get("parameters")}


def loaded(client: httpx.Client, api_base: str, model: str) -> list[dict]:
    models = client.get(f"{api_base}/api/ps").json().get("models", [])
    return [
        {k: m.get(k) for k in ("name", "context_length", "size", "size_vram")}
        for m in models
        if model in (m.get("name"), m.get("model"))
    ]


def write_private(path: Path, data: dict) -> None:
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(fd, "w", encoding="utf-8") as handle:
        handle.write(json.dumps(data, ensure_ascii=False, indent=1))


def run(args: argparse.Namespace) -> int:
    record = json.loads(args.capture.read_text(encoding="utf-8"))
    gate = fidelity_gate(record)
    impl = args.impl_context.read_text(encoding="utf-8") if args.impl_context else None
    arms = plan_arms(record, impl, args.ctx, args.impl_ctx, args.seed)
    ollama_env = record["environment"].get("ollama") or {}
    expected_digest = (ollama_env.get("tag") or {}).get("digest")
    plan = {
        "gate": gate,
        "expected_digest": expected_digest,
        "arms": [
            {k: a[k] for k in ("arm_id", "evidence", "context_bytes", "options")}
            for a in arms
        ],
    }
    print(json.dumps(plan, indent=1))
    if not gate["passed"]:
        print("fidelity gate failed: nothing sent", file=sys.stderr)
        return 2
    if args.dry_run:
        return 0
    if not args.authorized:
        print("refusing to send GPU requests without --authorized", file=sys.stderr)
        return 3
    if not args.api_base:
        print("--api-base is required to run", file=sys.stderr)
        return 2
    model = gate["model"]
    api_base = args.api_base.rstrip("/")
    args.out_dir.mkdir(parents=True, exist_ok=True)
    with httpx.Client(timeout=args.timeout) as client:
        state = server_state(client, api_base, model)
        if expected_digest and state["digest"] != expected_digest:
            print(
                f"model digest changed: {state['digest']}: nothing sent",
                file=sys.stderr,
            )
            return 4
        for arm in arms:
            started = time.monotonic()
            when = datetime.now(timezone.utc).isoformat()
            error = None
            try:
                resp = client.post(
                    f"{api_base}/api/generate",
                    content=arm["body"],
                    headers={"Content-Type": "application/json"},
                )
                status, body_json = resp.status_code, resp.json()
            except (httpx.HTTPError, ValueError) as exc:
                status, body_json, error = None, None, repr(exc)
            wall_ms = round((time.monotonic() - started) * 1000, 1)
            result = {
                "schema": SCHEMA,
                "arm_id": arm["arm_id"],
                "sent_at": when,
                "source_capture_id": record.get("capture_id"),
                "evidence": arm["evidence"],
                "context_bytes": arm["context_bytes"],
                "context_sha256": arm["context_sha256"],
                "options": arm["options"],
                "request_body_sha256": sha256(arm["body"]),
                "request_body_text": arm["body"].decode("utf-8"),
                "status_code": status,
                "error": error,
                "wall_ms": wall_ms,
                "response": body_json,
                "ps_after_call": loaded(client, api_base, model),
                "server_state": state,
            }
            write_private(args.out_dir / f"{arm['arm_id']}.json", result)
            r = body_json or {}
            print(
                arm["arm_id"],
                status,
                r.get("done_reason"),
                r.get("prompt_eval_count"),
                r.get("eval_count"),
                wall_ms,
                flush=True,
            )
    return 0


def summarize(args: argparse.Namespace) -> int:
    key = json.loads(args.answer_key.read_text(encoding="utf-8"))
    rows = []
    for path in sorted(args.dir.glob("*.json")):
        rec = json.loads(path.read_text(encoding="utf-8"))
        if rec.get("schema") != SCHEMA:
            continue
        r = rec.get("response") or {}
        body = json.loads(rec["request_body_text"])
        context, query = split_user_message(
            body["prompt"].split("\n\n### User:\n", 1)[1].removesuffix("\n\n")
        )
        answer = r.get("response") or ""
        ps = (rec.get("ps_after_call") or [{}])[0]
        rows.append(
            {
                "arm_id": rec["arm_id"],
                "num_ctx_sent": rec["options"].get("num_ctx"),
                "context_length_loaded": ps.get("context_length"),
                "size_vram": ps.get("size_vram"),
                "done_reason": r.get("done_reason"),
                "prompt_eval_count": r.get("prompt_eval_count"),
                "eval_count": r.get("eval_count"),
                "load_s": round((r.get("load_duration") or 0) / 1e9, 1),
                "prompt_eval_s": round((r.get("prompt_eval_duration") or 0) / 1e9, 1),
                "eval_s": round((r.get("eval_duration") or 0) / 1e9, 1),
                "total_s": round((r.get("total_duration") or 0) / 1e9, 1),
                "thinking_chars": len(r.get("thinking") or ""),
                "answer_chars": len(answer),
                **score(answer, context, key, query),
            }
        )
    print(json.dumps(rows, indent=1))
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=(__doc__ or "").split("\n\n")[0])
    sub = parser.add_subparsers(dest="cmd", required=True)

    b = sub.add_parser("build-context")
    b.add_argument("--commit", default=INGESTED_COMMIT)
    b.add_argument("--out", type=Path, required=True)

    r = sub.add_parser("run")
    r.add_argument("capture", type=Path)
    r.add_argument("--api-base")
    r.add_argument("--impl-context", type=Path)
    r.add_argument("--out-dir", type=Path, required=True)
    r.add_argument("--ctx", type=int, action="append", default=None)
    r.add_argument("--impl-ctx", type=int, action="append", default=None)
    r.add_argument("--seed", type=int, action="append", default=None)
    r.add_argument("--timeout", type=float, default=900)
    r.add_argument("--dry-run", action="store_true")
    r.add_argument("--authorized", action="store_true")

    s = sub.add_parser("summarize")
    s.add_argument("dir", type=Path)
    s.add_argument("--answer-key", type=Path, required=True)

    args = parser.parse_args(argv)
    if args.cmd == "build-context":
        text = build_context(args.commit)
        args.out.write_text(text, encoding="utf-8", newline="\n")
        print(json.dumps({"bytes": len(text.encode("utf-8")), "sha256": sha256(text)}))
        return 0
    if args.cmd == "run":
        args.ctx = args.ctx or [4096, 8192, 16384]
        args.impl_ctx = args.impl_ctx or [8192, 16384]
        args.seed = args.seed or [11, 23]
        return run(args)
    return summarize(args)


if __name__ == "__main__":
    sys.exit(main())
