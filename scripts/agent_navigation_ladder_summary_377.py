"""Mechanical support metrics for every ladder run (#377).

    python scripts/agent_navigation_ladder_summary_377.py \
        EXPECTED_CHAINS CHECKOUT LADDER_DIR

LADDER_DIR holds ``<tier>/<run>/<qid>.json``. Writes
``LADDER_DIR/support.json`` and prints one row per answer.

Metrics per answer: witness coverage (strict and lenient, core and
supporting) from the #375 scorer, the share of cited quotes found in the
named file, and the share of in-repository callees whose function or class
name is defined in the file the answer names.
"""

import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from agent_navigation_score_375 import score_question  # noqa: E402


def callee_located(rel: dict, checkout: Path) -> bool | None:
    """True/False for in-repository callees; None when not checkable."""
    cfile = str(rel.get("callee_file", "")).replace("\\", "/").strip()
    name = re.sub(r"\(.*?\)", "", str(rel.get("callee_function", ""))).strip()
    if not cfile.endswith(".py") or not name:
        return None
    path = checkout / cfile
    if not path.is_file():
        return False
    parts = [p for p in re.split(r"[.\s]+", name) if p.isidentifier()]
    if not parts:
        return None
    text = path.read_text(encoding="utf-8", errors="replace")
    leaf = parts[-1]
    if re.search(rf"^\s*(async\s+def|def|class)\s+{re.escape(leaf)}\b", text, re.M):
        return True
    if re.search(rf"^{re.escape(leaf)}\s*[:=]", text, re.M):
        return True  # module-level binding
    # Inherited dunder or method: accept when the named class is in the file.
    owner = parts[-2] if len(parts) > 1 else ""
    return bool(owner and re.search(rf"^\s*class\s+{re.escape(owner)}\b", text, re.M))


def frac(num: int, den: int) -> float | None:
    return round(num / den, 3) if den else None


def main() -> None:
    chains = json.loads(Path(sys.argv[1]).read_text(encoding="utf-8"))["chains"]
    checkout, ladder = Path(sys.argv[2]), Path(sys.argv[3])
    rows = []
    for answer in sorted(ladder.glob("*/*/H-*.json")):
        tier, run, qid = answer.parts[-3], answer.parts[-2], answer.stem
        data = json.loads(answer.read_text(encoding="utf-8"))
        rels = [r for r in data.get("relationships", []) if isinstance(r, dict)]
        score = score_question(chains[qid], rels, checkout)
        located = [callee_located(r, checkout) for r in rels]
        checkable = [x for x in located if x is not None]
        row = {
            "tier": tier,
            "run": run,
            "qid": qid,
            "stop": data.get("stop", "submitted"),
            "answer_chars": len(data.get("answer", "")),
            "relationships": len(rels),
            "quote_verified": frac(len(rels) - score["quotes_unverified"], len(rels)),
            "callee_located": frac(sum(checkable), len(checkable)),
            "core_strict": score["core_strict"],
            "core_lenient": score["core_lenient"],
            "supporting_lenient": score["supporting_lenient"],
            "missed": [m["id"] for m in score["missed"]],
        }
        rows.append(row)
        print(json.dumps(row))
    (ladder / "support.json").write_text(json.dumps(rows, indent=1), encoding="utf-8")


if __name__ == "__main__":
    main()
