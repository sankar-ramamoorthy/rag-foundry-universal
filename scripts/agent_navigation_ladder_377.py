"""Minimal source-navigation tool loop over LiteLLM (#377).

Runs one question against one model with four read-only tools confined to a
source checkout, and records the answer, token usage, cost and wall time.

    python scripts/agent_navigation_ladder_377.py \
        --model zai/glm-4.7-flash --checkout PATH/mealie \
        --questions DOCS/evaluations/359-H/questions.json --qid H-1 \
        --out OUT_DIR

Credentials are read by LiteLLM from the environment (for example
ZAI_API_KEY), or from the variable named by --api-key-env for an
OpenAI-compatible endpoint given with --api-base. Nothing here stores them.
--price-in/--price-out record a cost at published rates when LiteLLM has no
price for the model.
"""

import argparse
import fnmatch
import json
import os
import re
import time
from pathlib import Path
from typing import Any

import litellm

MAX_TOOL_CHARS = 12000

SYSTEM = """You are answering one code-comprehension question about a Python \
web application, as a measured experiment.

Rules:
- Use only the provided tools (list_dir, find_files, grep, read_file). They \
are confined to the source checkout.
- Base the answer on the implementation source you actually read, not on \
prior knowledge of the project, its docs, or its tests. Every claim must be \
backed by a line you opened in this session.
- Follow each call to its real definition. When a call goes through an \
injected dependency, an attribute, a base class, a generic or a callback, \
work out which concrete function runs and cite where that binding is \
established.
- Also establish how the public URL path is composed (where each prefix \
segment comes from).

When you are done, call submit_answer exactly once. List every \
caller-to-callee step in the execution path as its own relationship entry, \
including the route decorator, router inclusion lines, each call inside each \
function on the path, and the database and external-service calls at the \
leaves. Be complete: one entry per call site, not one per function. Quotes \
are checked mechanically against the files, so copy them exactly."""

REL_PROPS = {
    "caller_file": {"type": "string", "description": "path relative to root"},
    "caller_function": {"type": "string"},
    "line": {"type": "integer", "description": "1-based line in caller_file"},
    "quote": {"type": "string", "description": "exact source line, verbatim"},
    "callee_file": {"type": "string", "description": "file, or 'external'"},
    "callee_function": {"type": "string"},
    "kind": {
        "type": "string",
        "description": "direct_call | deferred_callback | database_operation"
        " | external_service_call | route_registration | dependency_binding"
        " | other",
    },
}


def tool(name: str, description: str, props: dict, required: list[str]) -> dict:
    return {
        "type": "function",
        "function": {
            "name": name,
            "description": description,
            "parameters": {
                "type": "object",
                "properties": props,
                "required": required,
            },
        },
    }


TOOLS = [
    tool(
        "list_dir",
        "List entries of a directory (relative to the checkout root).",
        {"path": {"type": "string"}},
        ["path"],
    ),
    tool(
        "find_files",
        "Find files whose relative path matches a glob such as "
        "'mealie/routes/**/*.py' or '**/exports.py'.",
        {"pattern": {"type": "string"}},
        ["pattern"],
    ),
    tool(
        "grep",
        "Regex search in files. Returns 'path:line: text' matches. 'path' is "
        "a file or directory relative to the root; 'include' is an optional "
        "filename glob such as '*.py'.",
        {
            "pattern": {"type": "string"},
            "path": {"type": "string"},
            "include": {"type": "string"},
        },
        ["pattern"],
    ),
    tool(
        "read_file",
        "Read a file with line numbers. Optional 1-based 'offset' and "
        "'limit' (default 250 lines).",
        {
            "path": {"type": "string"},
            "offset": {"type": "integer"},
            "limit": {"type": "integer"},
        },
        ["path"],
    ),
    tool(
        "submit_answer",
        "Submit the final answer. Call once, when finished.",
        {
            "answer": {
                "type": "string",
                "description": "full prose answer with file:line citations",
            },
            "relationships": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": REL_PROPS,
                    "required": ["caller_file", "line", "quote"],
                },
            },
            "uncertain": {"type": "array", "items": {"type": "string"}},
        },
        ["answer", "relationships"],
    ),
]


class Sandbox:
    def __init__(self, root: Path) -> None:
        self.root = root.resolve()

    def resolve(self, rel: str) -> Path:
        path = (self.root / (rel or ".")).resolve()
        if path != self.root and self.root not in path.parents:
            raise ValueError("path is outside the checkout")
        return path

    def rel(self, path: Path) -> str:
        return path.relative_to(self.root).as_posix()

    def walk(self, start: Path):
        for path in sorted(start.rglob("*")):
            parts = path.relative_to(self.root).parts
            if ".git" in parts or "node_modules" in parts:
                continue
            if path.is_file():
                yield path

    def list_dir(self, path: str = ".") -> str:
        target = self.resolve(path)
        rows = [
            p.name + ("/" if p.is_dir() else "")
            for p in sorted(target.iterdir())
            if p.name != ".git"
        ]
        return "\n".join(rows)

    def find_files(self, pattern: str) -> str:
        hits = [
            self.rel(p)
            for p in self.walk(self.root)
            if fnmatch.fnmatch(self.rel(p), pattern)
            or fnmatch.fnmatch(self.rel(p), pattern.replace("**/", ""))
        ]
        return "\n".join(hits[:300]) or "no files"

    def grep(self, pattern: str, path: str = ".", include: str = "") -> str:
        rx = re.compile(pattern)
        target = self.resolve(path)
        files = [target] if target.is_file() else self.walk(target)
        out: list[str] = []
        for file in files:
            if include and not fnmatch.fnmatch(file.name, include):
                continue
            try:
                text = file.read_text(encoding="utf-8")
            except (UnicodeDecodeError, OSError):
                continue
            for number, line in enumerate(text.splitlines(), 1):
                if rx.search(line):
                    out.append(f"{self.rel(file)}:{number}: {line.strip()[:240]}")
                    if len(out) >= 150:
                        return "\n".join(out) + "\n[truncated at 150 matches]"
        return "\n".join(out) or "no matches"

    def read_file(self, path: str, offset: int = 1, limit: int = 250) -> str:
        lines = self.resolve(path).read_text(encoding="utf-8").splitlines()
        start = max(1, int(offset or 1))
        end = min(len(lines), start + min(int(limit or 250), 400) - 1)
        body = "\n".join(f"{i}\t{lines[i - 1]}" for i in range(start, end + 1))
        return f"{body}\n[lines {start}-{end} of {len(lines)}]"


def call_tool(sandbox: Sandbox, name: str, args: dict) -> str:
    try:
        result = getattr(sandbox, name)(**args)
    except Exception as exc:  # reported to the model, which may retry
        return f"error: {type(exc).__name__}: {exc}"
    if len(result) > MAX_TOOL_CHARS:
        result = result[:MAX_TOOL_CHARS] + "\n[output truncated]"
    return result


def complete(model: str, messages: list, retries: int, extra: dict) -> Any:
    delay = 5.0
    for attempt in range(retries + 1):
        try:
            return litellm.completion(
                model=model, messages=messages, tools=TOOLS, timeout=300, **extra
            )
        except Exception as exc:
            if attempt == retries:
                raise
            print(f"  retry {attempt + 1}: {type(exc).__name__}: {str(exc)[:160]}")
            time.sleep(delay)
            delay = min(delay * 2, 60)


def step_cost(response) -> float:
    try:
        return float(litellm.completion_cost(completion_response=response) or 0)
    except Exception:
        return 0.0


def add_usage(totals: dict, response) -> None:
    usage = getattr(response, "usage", None)
    totals["prompt_tokens"] += getattr(usage, "prompt_tokens", 0) or 0
    totals["completion_tokens"] += getattr(usage, "completion_tokens", 0) or 0
    totals["litellm_cost_usd"] += step_cost(response)
    totals["model_calls"] += 1


def parse_args(raw: str) -> dict:
    try:
        value = json.loads(raw or "{}")
    except json.JSONDecodeError:
        return {}
    return value if isinstance(value, dict) else {}


def run(args: argparse.Namespace) -> dict:
    questions = json.loads(Path(args.questions).read_text(encoding="utf-8"))
    question = next(q for q in questions["questions"] if q["qid"] == args.qid)
    sandbox = Sandbox(Path(args.checkout))
    messages: list = [
        {"role": "system", "content": SYSTEM},
        {"role": "user", "content": "Question:\n" + question["question"]},
    ]
    totals = {
        "prompt_tokens": 0,
        "completion_tokens": 0,
        "litellm_cost_usd": 0.0,
        "model_calls": 0,
    }
    extra = json.loads(args.extra) if args.extra else {}
    if args.api_base:
        extra["api_base"] = args.api_base
    if args.api_key_env:
        extra["api_key"] = os.environ[args.api_key_env]
    record: dict = {"qid": args.qid, "model": args.model, "stop": "max_steps"}
    tool_calls = 0
    started = time.time()
    submitted = None
    for _ in range(args.max_steps):
        if time.time() - started > args.max_seconds:
            record["stop"] = "max_seconds"
            break
        try:
            response = complete(args.model, messages, args.retries, extra)
        except Exception as exc:
            record["stop"] = f"error: {type(exc).__name__}: {str(exc)[:300]}"
            break
        add_usage(totals, response)
        message = response.choices[0].message
        calls = message.tool_calls or []
        messages.append(message.model_dump(exclude_none=True))
        if not calls:
            record["stop"] = "no_tool_call"
            record["final_text"] = message.content
            break
        for call in calls:
            tool_calls += 1
            call_args = parse_args(call.function.arguments)
            name = str(call.function.name or "")
            if name == "submit_answer":
                submitted = call_args
                result = "received"
            else:
                result = call_tool(sandbox, name, call_args)
            messages.append(
                {"role": "tool", "tool_call_id": call.id, "content": result}
            )
        if submitted is not None:
            record["stop"] = "submitted"
            break
    submitted = submitted or {}
    record.update(
        {
            "answer": submitted.get("answer", ""),
            "relationships": submitted.get("relationships", []),
            "uncertain": submitted.get("uncertain", []),
            "tool_calls": tool_calls,
            "wall_seconds": round(time.time() - started, 1),
            "usage": totals,
            "published_rate_cost_usd": round(
                (
                    totals["prompt_tokens"] * args.price_in
                    + totals["completion_tokens"] * args.price_out
                )
                / 1e6,
                5,
            ),
            "transcript": messages,
        }
    )
    return record


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--model", required=True)
    parser.add_argument("--checkout", required=True)
    parser.add_argument("--questions", required=True)
    parser.add_argument("--qid", required=True)
    parser.add_argument("--out", required=True)
    parser.add_argument("--max-steps", type=int, default=80)
    parser.add_argument("--max-seconds", type=int, default=1500)
    parser.add_argument("--retries", type=int, default=6)
    parser.add_argument("--extra", default="", help="JSON of extra LiteLLM kwargs")
    parser.add_argument("--api-base", default="", help="OpenAI-compatible base URL")
    parser.add_argument(
        "--api-key-env", default="", help="name of the env var holding the key"
    )
    parser.add_argument(
        "--price-in", type=float, default=0.0, help="USD per 1M input tokens"
    )
    parser.add_argument(
        "--price-out", type=float, default=0.0, help="USD per 1M output tokens"
    )
    args = parser.parse_args()
    record = run(args)
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    (out / f"{args.qid}.json").write_text(
        json.dumps(record, indent=1, default=str), encoding="utf-8"
    )
    summary = {k: record[k] for k in ("qid", "model", "stop", "tool_calls")}
    summary.update(
        relationships=len(record["relationships"]),
        wall_seconds=record["wall_seconds"],
        usage=record["usage"],
        published_rate_cost_usd=record["published_rate_cost_usd"],
    )
    print(json.dumps(summary))


if __name__ == "__main__":
    main()
