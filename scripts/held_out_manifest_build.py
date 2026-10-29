"""Build and validate the draft E1 held-out manifest (issue #281).

Reads the authored case specs, extracts each function's source from the pinned
clones, and checks the declaration (DOCS/evaluations/code-evidence-held-out/
stratification.md): every expression is a verbatim substring of its function
whose first line occurs once; operations and dependencies per case are in range;
strata are measured by static analysis; the quotas hold. Byte costs, retrieval
output and control results are never computed or read.

    python scripts/held_out_manifest_build.py --clones DIR [--write]
"""

from __future__ import annotations

import argparse
import ast
import hashlib
import json
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parents[1]
HELD_OUT = HERE / "DOCS/evaluations/code-evidence-held-out"
SPECS = HELD_OUT / "cases"
OUT = HELD_OUT / "manifest.draft.json"
RECORD = json.loads((HELD_OUT / "selection-scan.json").read_text(encoding="utf-8"))
FUNCS = (ast.FunctionDef, ast.AsyncFunctionDef)
LONG_BODY, SHORT_BODY, LONG_SIG, WIDE, NARROW = 120, 40, 8, 60, 25
EXCLUDED = {"HKUDS/LightRAG", "sankar-ramamoorthy/rag-foundry-universal",
            "sankar-ramamoorthy/py-coding-agent"}
# Evaluation limitations recorded at the independent review; the selected functions
# are deliberately NOT replaced because of them (declaration section 8).
KNOWN_LIMITATIONS = [
    "Concentration: three of pypa/hatch's four cases (H1, H2, H4) are `hatch env` "
    "click commands with decorator-heavy signatures; the fourth (H3) is a release "
    "script. Hatch results characterise those commands, not the repository broadly.",
    "Overlap: P2 and P4 both live in tools/dumppdf.py and both involve dumpxml, so "
    "they are not independent observations.",
    "Narrow coverage: three of pdfminer.six's four cases are command-line utilities "
    "under tools/, not library modules.",
    "Training-data exposure: pallets/werkzeug is very likely well represented in "
    "model training data despite its star count.",
    "Source text is the pinned function source, not the stored DocumentNode.text; "
    "that comparison happens at ingestion time.",
]


def pins() -> dict[str, dict]:
    out = {}
    for dom in RECORD["domains"].values():
        row = next(r for r in dom["log"] if r["decision"] == "SELECTED")
        out[row["repo"]] = {"commit": row["commit"], "license": row["license"],
                            "stars_at_selection": row["stars"]}
    return out


def find_function(tree: ast.Module, name: str) -> ast.AST:
    for node in tree.body:
        if isinstance(node, FUNCS) and node.name == name:
            return node
    raise KeyError(f"module-level function {name!r} not found")


def load_source(clone: Path, canonical_id: str) -> dict:
    rel, name = canonical_id.split("#")
    text = (clone / rel).read_text(encoding="utf-8")
    tree = ast.parse(text)
    node = find_function(tree, name)
    start = min([d.lineno for d in node.decorator_list] + [node.lineno])
    lines = text.split("\n")[start - 1: node.end_lineno]
    body = "\n".join(lines)
    return {"relative_path": rel, "start_line": start, "end_line": node.end_lineno,
            "text": body, "sha256": hashlib.sha256(body.encode()).hexdigest(),
            "_node": node, "_tree": tree,
            "metrics": {"lines": node.end_lineno - node.lineno + 1,
                        "signature": node.body[0].lineno - start}}


def contexts(node: ast.AST, line: int) -> set[str]:
    """Constructs that enclose absolute file ``line`` inside ``node``."""
    found: set[str] = set()
    for n in ast.walk(node):
        if isinstance(n, ast.If):
            if any(s.lineno <= line <= s.end_lineno for s in n.orelse):
                found.add("else_elif")
        elif isinstance(n, ast.Try):
            parts = [*n.body, *n.handlers, *n.orelse, *n.finalbody]
            if any(s.lineno <= line <= s.end_lineno for s in parts):
                found.add("try")
        elif isinstance(n, (ast.For, ast.While, ast.AsyncFor, ast.With,
                            ast.AsyncWith)):
            if any(s.lineno <= line <= s.end_lineno for s in n.body):
                found.add("loop_with")
    return found


def locate(src: dict, expr: str) -> tuple[int, set[str]]:
    lines = src["text"].split("\n")
    if "\n" in expr:
        raise ValueError(f"multi-line expression not supported: {expr[:40]!r}")
    hits = [i for i, ln in enumerate(lines) if expr in ln]
    if len(hits) != 1:
        raise ValueError(f"{len(hits)} occurrences (need exactly 1): {expr[:70]!r}")
    absolute = src["start_line"] + hits[0]
    return absolute, contexts(src["_node"], absolute)


def build_case(spec: dict, clones: Path, sources: dict) -> dict:
    owner, name = spec["repo"].split("/")
    clone = clones / f"{owner}__{name}"
    ctx: set[str] = set()
    per_function: dict[str, list[int]] = {}
    items = {"operations": spec["operations"], "dependencies": spec["dependencies"]}
    for group in items.values():
        for entry in group:
            cid = entry["canonical_id"]
            sources.setdefault(cid, load_source(clone, cid))
            entry["located"] = []
            for expr in entry["expressions"]:
                line, found = locate(sources[cid], expr)
                entry["located"].append(line)
                per_function.setdefault(cid, []).append(line)
                ctx |= found
    primary = max(per_function, key=lambda c: len(per_function[c]))
    p = sources[primary]
    spread = max(max(v) - min(v) for v in per_function.values())
    return {
        "id": spec["id"], "repo": spec["repo"], "slot": spec["slot"],
        "style": spec["style"], "query": spec["query"],
        "revisions": spec.get("revisions", []),
        "functions": sorted(per_function), "primary_function": primary,
        "operations": spec["operations"], "dependencies": spec["dependencies"],
        "strata": {"primary_lines": p["metrics"]["lines"],
                   "primary_signature_lines": p["metrics"]["signature"],
                   "max_witness_spread": spread, "functions_needed": len(per_function),
                   "contexts": sorted(ctx),
                   "any_long_signature": any(sources[c]["metrics"]["signature"]
                                             >= LONG_SIG for c in per_function)},
    }


def quota_report(cases: list[dict]) -> dict:
    def n(pred) -> int:
        return sum(1 for c in cases if pred(c))
    s = lambda c: c["strata"]  # noqa: E731
    q1 = lambda c: (2 <= s(c)["functions_needed"] <= 3  # noqa: E731
                    and s(c)["any_long_signature"])
    q2 = lambda c: (s(c)["primary_lines"] >= LONG_BODY  # noqa: E731
                    and s(c)["max_witness_spread"] >= WIDE)
    q3 = lambda c: (s(c)["primary_lines"] < SHORT_BODY  # noqa: E731
                    and s(c)["max_witness_spread"] < NARROW)
    per_repo: dict[str, dict[str, int]] = {}
    for c in cases:
        r = per_repo.setdefault(c["repo"], {"q1": 0, "q2": 0, "q3": 0, "cases": 0})
        r["cases"] += 1
        r["q1"] += q1(c)
        r["q2"] += q2(c)
        r["q3"] += q3(c)
    return {
        "cases": len(cases), "repos": sorted(per_repo), "per_repo": per_repo,
        "Q1_multi_function_long_signature": n(q1),
        "Q2_long_function_wide_spread": n(q2),
        "Q3_short_function_narrow": n(q3),
        "Q4_else_elif": n(lambda c: "else_elif" in s(c)["contexts"]),
        "Q4_try": n(lambda c: "try" in s(c)["contexts"]),
        "Q4_loop_with": n(lambda c: "loop_with" in s(c)["contexts"]),
        "Q5_methods": 0,
        "Q6_natural_language": n(lambda c: c["style"] == "natural"),
    }


def repo_problems(q: dict) -> list[str]:
    out = []
    if q["cases"] != 12 or len(q["repos"]) != 3:
        out.append("need exactly 12 cases over 3 repositories")
    for repo, r in q["per_repo"].items():
        if r["cases"] != 4:
            out.append(f"{repo}: {r['cases']} cases (need 4)")
        if not (r["q1"] or r["q2"] or r["q3"]):
            out.append(f"{repo}: contributes to none of Q1-Q3")
        if max(r["q1"], r["q2"], r["q3"]) > 2:
            out.append(f"{repo}: more than two cases in one of Q1/Q2/Q3")
    return out


def quota_problems(q: dict) -> list[str]:
    floors = (("Q1_multi_function_long_signature", 2),
              ("Q2_long_function_wide_spread", 3), ("Q3_short_function_narrow", 2),
              ("Q4_else_elif", 3), ("Q4_try", 2), ("Q4_loop_with", 2),
              ("Q6_natural_language", 4))
    return [f"{k} = {q[k]} (need >= {f})" for k, f in floors if q[k] < f]


def case_problems(c: dict) -> list[str]:
    out = []
    if not 4 <= len(c["operations"]) <= 5:
        out.append(f"{c['id']}: {len(c['operations'])} operations (need 4-5)")
    if not 3 <= len(c["dependencies"]) <= 4:
        out.append(f"{c['id']}: {len(c['dependencies'])} dependencies (need 3-4)")
    if c["repo"] in EXCLUDED:
        out.append(f"{c['id']}: excluded repository")
    return out


def problems(cases: list[dict], q: dict) -> list[str]:
    out = repo_problems(q) + quota_problems(q)
    for c in cases:
        out += case_problems(c)
    return out


def verify_clone(clones: Path, repo: str, commit: str) -> None:
    owner, name = repo.split("/")
    clone = clones / f"{owner}__{name}"
    # core.longpaths: the scratch path exceeds the Windows limit for .git/objects
    git = ["git", "-c", "core.longpaths=true", "-C", str(clone)]
    head = subprocess.run([*git, "rev-parse", "HEAD"], capture_output=True,
                          text=True, check=True).stdout.strip()
    dirty = subprocess.run([*git, "status", "--porcelain"], capture_output=True,
                           text=True, check=True).stdout.strip()
    if head != commit or dirty:
        raise SystemExit(f"{repo}: clone is not clean at the pinned commit {commit}")


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--clones", type=Path, required=True)
    ap.add_argument("--write", action="store_true")
    args = ap.parse_args()
    pinned = pins()
    for repo, p in pinned.items():
        verify_clone(args.clones, repo, p["commit"])
    sources: dict[str, dict] = {}
    cases = [build_case(json.loads(f.read_text(encoding="utf-8")), args.clones, sources)
             for f in sorted(SPECS.glob("*.json"))]
    q = quota_report(cases)
    issues = problems(cases, q)
    print(json.dumps(q, indent=1))
    print("PROBLEMS:" if issues else "all declared checks pass", *issues, sep="\n  ")
    if args.write and not issues:
        public = {cid: {k: v for k, v in s.items() if not k.startswith("_")}
                  for cid, s in sorted(sources.items())}
        OUT.write_text(json.dumps({
            "status": "draft-awaiting-second-review",
            "dataset_role": "held-out; not frozen until reviewed (stratification s9)",
            "pins": pinned, "quota_report": q, "known_limitations": KNOWN_LIMITATIONS,
            "cases": cases, "sources": public},
            indent=1, ensure_ascii=False) + "\n", encoding="utf-8")
        print("wrote", OUT.relative_to(HERE))
    return 1 if issues else 0


if __name__ == "__main__":
    sys.exit(main())
