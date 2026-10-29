"""Deterministic held-out repository selection scan (issue #281).

Implements section 4-6 of DOCS/evaluations/code-evidence-held-out/stratification.md
exactly: per domain, query GitHub per permitted license, merge, sort by stars
descending, take the first 30, apply the eligibility filters in list order, run
the shape-availability scan on the first repository that passes, and take the
first that also passes it. Public metadata and static analysis (``ast``) only: no
retrieval output, no oracle byte costs, nothing from the evaluation stack.

Cloned code is only parsed, never executed. Clones go into ``--scratch``.

    python scripts/held_out_selection_scan.py --scratch DIR --out result.json
"""

from __future__ import annotations

import argparse
import ast
import json
import re
import subprocess
import sys
from datetime import date, timedelta
from pathlib import Path

DOMAINS = (("D1", "cli"), ("D2", "http"), ("D3", "parser"))
LICENSES = ("mit", "apache-2.0", "bsd-3-clause", "bsd-2-clause")
STARS = "300..8000"
EXCLUDED = {"lightrag", "rag-foundry-universal", "py-coding-agent"}
BLOCKED_WORDS = re.compile(
    r"\b(rag|llm|llms|agent|agents|langchain|openai|chatgpt|gpt|retrieval|"
    r"embedding|embeddings|genai|copilot|autogpt)\b", re.I)
SKIP_DIRS = {"tests", "test", "testing", "docs", "doc", "examples", "example",
             "vendor", "vendored", "third_party", "thirdparty", "build", "dist",
             "venv", ".venv", "site-packages", "node_modules", ".git", "__pycache__"}
MIN_FILES, MAX_FILES = 30, 400
LONG_BODY, SHORT_BODY, LONG_SIGNATURE = 120, 40, 8
FUNCS = (ast.FunctionDef, ast.AsyncFunctionDef)
BRANCHY = (ast.If, ast.Try, ast.With, ast.AsyncWith, ast.For, ast.While)
REPO_ROOT = Path(__file__).resolve().parents[1]


def run(*cmd: str, cwd: Path | None = None) -> str:
    return subprocess.run(cmd, capture_output=True, text=True, check=True,
                          cwd=cwd, encoding="utf-8", errors="replace").stdout


def search(topic: str, lic: str) -> tuple[str, list[dict]]:
    q = (f"language:python topic:{topic} stars:{STARS} archived:false "
         f"license:{lic}")
    out = run("gh", "api", "-X", "GET", "search/repositories", "-f", f"q={q}",
              "-f", "sort=stars", "-f", "order=desc", "-f", "per_page=30")
    return q, json.loads(out)["items"]


def candidates(topic: str) -> tuple[list[str], list[dict]]:
    queries, merged = [], {}
    for lic in LICENSES:
        q, items = search(topic, lic)
        queries.append(q)
        for it in items:
            merged.setdefault(it["full_name"], it)
    ranked = sorted(merged.values(), key=lambda i: -i["stargazers_count"])
    return queries, ranked[:30]


def referenced_in_project(full_name: str) -> bool:
    out = subprocess.run(
        ["git", "grep", "-i", "-F", "-l", full_name, "--", "DOCS", "specs",
         "scripts", "tests", ".specify", "README.md"],
        capture_output=True, text=True, cwd=REPO_ROOT, encoding="utf-8",
        errors="replace").stdout
    return bool(out.strip())


def metadata_reject(c: dict, chosen: set[str]) -> str | None:
    name = c["name"].lower()
    text = " ".join([c.get("description") or "", *c.get("topics", [])])
    cutoff = (date.today() - timedelta(days=3 * 365)).isoformat()
    if name in EXCLUDED:
        return "excluded development repository"
    if c["full_name"] in chosen:
        return "already chosen for an earlier domain"
    if referenced_in_project(c["full_name"]):
        return "referenced elsewhere in this project"
    if BLOCKED_WORDS.search(text):
        return "retrieval/LLM/RAG/agent framework by description or topics"
    if c["pushed_at"][:10] < cutoff:
        return f"no push since {cutoff}"
    return None


def clone(c: dict, dest: Path) -> str:
    target = dest / c["full_name"].replace("/", "__")
    if not target.exists():
        run("git", "-c", "core.longpaths=true", "clone", "--depth", "1", "--quiet",
            c["clone_url"], str(target))
    return run("git", "rev-parse", "HEAD", cwd=target).strip()


def source_files(root: Path) -> list[Path]:
    files = []
    for p in root.rglob("*.py"):
        rel = p.relative_to(root).parts
        if any(part in SKIP_DIRS for part in rel[:-1]):
            continue
        n = p.name
        if n == "conftest.py" or n.startswith("test_") or n.endswith("_test.py"):
            continue
        if "_pb2" in n:
            continue
        files.append(p)
    return files


def function_facts(fn: ast.AST, called: set[str]) -> dict:
    node = fn  # type: ignore[assignment]
    start = min([d.lineno for d in node.decorator_list] + [node.lineno])
    body = getattr(node, "end_lineno", node.lineno) - node.lineno + 1
    signature = node.body[0].lineno - start
    branchy = any(isinstance(n, BRANCHY) for n in ast.walk(node))
    return {"lines": body, "signature": signature, "branchy": branchy,
            "calls": called}


def calls_in(fn: ast.AST) -> set[str]:
    return {n.func.id for n in ast.walk(fn)
            if isinstance(n, ast.Call) and isinstance(n.func, ast.Name)}


def scan_file(path: Path) -> dict:
    try:
        tree = ast.parse(path.read_text(encoding="utf-8", errors="replace"))
    except (SyntaxError, ValueError, RecursionError):
        return {"parsed": False}
    top = {n.name for n in tree.body if isinstance(n, FUNCS)}
    facts = []
    for n in ast.walk(tree):
        if isinstance(n, FUNCS):
            facts.append((n.name, function_facts(n, calls_in(n))))
    pair = any(c in top and c != name for name, f in facts for c in f["calls"])
    return {"parsed": True, "facts": [f for _, f in facts], "pair": pair}


def shape(root: Path) -> dict:
    counts = {"long_body": 0, "long_signature": 0, "short_branchy": 0,
              "caller_callee_files": 0, "unparsed": 0, "functions": 0}
    for p in source_files(root):
        r = scan_file(p)
        if not r["parsed"]:
            counts["unparsed"] += 1
            continue
        counts["caller_callee_files"] += int(r["pair"])
        for f in r["facts"]:
            counts["functions"] += 1
            counts["long_body"] += f["lines"] >= LONG_BODY
            counts["long_signature"] += f["signature"] >= LONG_SIGNATURE
            counts["short_branchy"] += f["lines"] < SHORT_BODY and f["branchy"]
    return counts


def shape_ok(c: dict) -> bool:
    return (c["long_body"] >= 2 and c["long_signature"] >= 1
            and c["short_branchy"] >= 2 and c["caller_callee_files"] >= 1)


def evaluate(c: dict, scratch: Path, chosen: set[str]) -> dict:
    row = {"repo": c["full_name"], "stars": c["stargazers_count"],
           "license": (c.get("license") or {}).get("spdx_id"),
           "pushed_at": c["pushed_at"][:10], "topics": c.get("topics", [])}
    reason = metadata_reject(c, chosen)
    if reason:
        return {**row, "decision": "rejected", "reason": reason}
    sha = clone(c, scratch)
    root = scratch / c["full_name"].replace("/", "__")
    n = len(source_files(root))
    row.update(commit=sha, source_files=n)
    if not MIN_FILES <= n <= MAX_FILES:
        return {**row, "decision": "rejected",
                "reason": f"{n} source files outside {MIN_FILES}-{MAX_FILES}"}
    s = shape(root)
    row["shape"] = s
    if not shape_ok(s):
        return {**row, "decision": "rejected", "reason": "shape availability"}
    return {**row, "decision": "SELECTED"}


def select_domain(topic: str, scratch: Path, chosen: set[str]) -> dict:
    queries, ranked = candidates(topic)
    log = []
    for c in ranked:
        row = evaluate(c, scratch, chosen)
        log.append(row)
        print(f"  {row['repo']:45} {row['decision']:9} {row.get('reason', '')}",
              flush=True)
        if row["decision"] == "SELECTED":
            break
    return {"topic": topic, "queries": queries, "candidates_considered": len(log),
            "pool_size": len(ranked), "log": log}


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--scratch", type=Path, required=True)
    ap.add_argument("--out", type=Path, required=True)
    args = ap.parse_args()
    args.scratch.mkdir(parents=True, exist_ok=True)
    chosen: set[str] = set()
    result = {"run_date": date.today().isoformat(), "domains": {}}
    for label, topic in DOMAINS:
        print(f"{label} topic:{topic}", flush=True)
        d = select_domain(topic, args.scratch, chosen)
        picked = [r for r in d["log"] if r["decision"] == "SELECTED"]
        d["selected"] = picked[0]["repo"] if picked else None
        if picked:
            chosen.add(picked[0]["repo"])
        result["domains"][label] = d
    args.out.write_text(json.dumps(result, indent=2), encoding="utf-8")
    return 0 if all(d["selected"] for d in result["domains"].values()) else 2


if __name__ == "__main__":
    sys.exit(main())
