"""Score source-navigation agent outputs against #359-H expected chains (#375).

Usage:
    python scripts/agent_navigation_score_375.py EXPECTED_CHAINS CHECKOUT OUT_DIR

OUT_DIR holds one ``<qid>.json`` per question with a ``relationships`` list.
A cited relationship is used only if its quote is present in the checkout
file it names (whitespace-normalised).

A witness is supported (strict) when a verified relationship names the
caller's file and function and its quote matches the witness regex. Lenient
drops the function-name requirement and also accepts a matching cited line
number in the caller's file.
"""

import json
import re
import sys
from pathlib import Path


def norm(text: str) -> str:
    return re.sub(r"\s+", " ", text).strip()


def rel_file(rel: dict) -> str:
    return str(rel.get("caller_file", "")).replace("\\", "/")


def quote_verified(rel: dict, checkout: Path) -> bool:
    path = checkout / rel_file(rel)
    quote = norm(str(rel.get("quote", "")))
    if not quote or not path.is_file():
        return False
    return quote in norm(path.read_text(encoding="utf-8", errors="replace"))


def score_witness(witness: dict, verified: list[dict]) -> dict:
    wfile, wfunc = witness["caller"].split("#", 1)
    leaf = wfunc.split(".")[-1]
    rx = re.compile(witness["witness_regex"])
    strict = lenient = False
    for rel in verified:
        if rel_file(rel) != wfile:
            continue
        hit = bool(rx.search(str(rel.get("quote", ""))))
        if hit or rel.get("line") in witness.get("lines", []):
            lenient = True
        if hit and leaf in str(rel.get("caller_function", "")):
            strict = True
    return {
        "id": witness["id"],
        "tier": witness["tier"],
        "resolution_class": witness.get("resolution_class"),
        "callee": witness["callee"],
        "strict": strict,
        "lenient": lenient,
    }


def count(rows: list[dict], tier: str, key: str) -> str:
    sel = [x for x in rows if x["tier"] == tier]
    return f"{sum(x[key] for x in sel)}/{len(sel)}"


def score_question(witnesses: list[dict], rels: list[dict], checkout: Path) -> dict:
    verified = [r for r in rels if quote_verified(r, checkout)]
    rows = [score_witness(w, verified) for w in witnesses]
    return {
        "cited_relationships": len(rels),
        "quotes_unverified": len(rels) - len(verified),
        "core_strict": count(rows, "core", "strict"),
        "core_lenient": count(rows, "core", "lenient"),
        "supporting_strict": count(rows, "supporting", "strict"),
        "supporting_lenient": count(rows, "supporting", "lenient"),
        "missed": [x for x in rows if not x["lenient"]],
        "witnesses": rows,
    }


def main() -> None:
    chains = json.loads(Path(sys.argv[1]).read_text(encoding="utf-8"))["chains"]
    checkout, out = Path(sys.argv[2]), Path(sys.argv[3])
    report = {}
    for qid, witnesses in chains.items():
        answer = out / f"{qid}.json"
        if not answer.exists():
            report[qid] = {"error": "no agent output"}
            continue
        rels = json.loads(answer.read_text(encoding="utf-8")).get("relationships", [])
        report[qid] = score_question(witnesses, rels, checkout)
    summary = {
        q: {k: v for k, v in r.items() if k != "witnesses"} for q, r in report.items()
    }
    print(json.dumps(summary, indent=1))
    (out / "score.json").write_text(json.dumps(report, indent=1), encoding="utf-8")


if __name__ == "__main__":
    main()
