"""Build blind grading bundles and merge grades for the #377 ladder.

    # 1. Blind bundles: one answers.md per question, labels shuffled.
    python scripts/agent_navigation_grade_bundle_377.py bundle LADDER_DIR GRADE_DIR

    # 2. After grading: merge grades, support metrics and the pass bar.
    python scripts/agent_navigation_grade_bundle_377.py merge LADDER_DIR GRADE_DIR \
        RUBRIC

``bundle`` writes GRADE_DIR/<qid>/answers.md (prose answers only, labelled
A, B, ...) and GRADE_DIR/key.json (label to tier/run), which the grader is
not given. ``merge`` expects GRADE_DIR/<qid>/grades.json and
LADDER_DIR/support.json, and writes GRADE_DIR/results.json.
"""

import json
import random
import string
import sys
from pathlib import Path

SEED = 377


def bundle(ladder: Path, grade: Path) -> None:
    key: dict = {}
    for qid in ("H-1", "H-2", "H-3"):
        answers = sorted(ladder.glob(f"*/*/{qid}.json"))
        random.Random(f"{SEED}-{qid}").shuffle(answers)
        parts = [f"# Answers to grade for {qid}\n"]
        key[qid] = {}
        for label, path in zip(string.ascii_uppercase, answers):
            data = json.loads(path.read_text(encoding="utf-8"))
            key[qid][label] = {"tier": path.parts[-3], "run": path.parts[-2]}
            text = data.get("answer") or "(no answer was submitted)"
            parts.append(f"\n\n===== ANSWER {label} =====\n\n{text}\n")
        out = grade / qid
        out.mkdir(parents=True, exist_ok=True)
        (out / "answers.md").write_text("".join(parts), encoding="utf-8")
        print(qid, len(answers), "answers")
    (grade / "key.json").write_text(json.dumps(key, indent=1), encoding="utf-8")


def ratio(text: str) -> tuple[int, int]:
    num, den = text.split("/")
    return int(num), int(den)


def merge(ladder: Path, grade: Path, rubric_path: Path) -> None:
    rubric = json.loads(rubric_path.read_text(encoding="utf-8"))
    bar = rubric["pass_bar"]
    key = json.loads((grade / "key.json").read_text(encoding="utf-8"))
    support = {
        (r["tier"], r["run"], r["qid"]): r
        for r in json.loads((ladder / "support.json").read_text(encoding="utf-8"))
    }
    results = []
    for qid, labels in key.items():
        grades = json.loads((grade / qid / "grades.json").read_text(encoding="utf-8"))
        total = len(rubric["questions"][qid])
        for label, who in labels.items():
            g = grades[label]
            verdicts = list(g["claims"].values())
            correct = verdicts.count("correct")
            contradicted = verdicts.count("contradicted")
            found = g.get("false_statements", [])
            false_statements = sum(
                1 for f in found if f.get("severity", "material") == "material"
            )
            minor = len(found) - false_statements
            s = support[(who["tier"], who["run"], qid)]
            core_ok, core_all = ratio(s["core_lenient"])
            checks = {
                "no_contradicted_claim": contradicted == 0,
                "no_material_false_statement": false_statements == 0,
                "claims_correct_fraction": correct / total
                >= bar["min_correct_fraction"],
                "all_core_witnesses": core_ok == core_all,
                "quotes_verified": (s["quote_verified"] or 0)
                >= bar["min_quote_verified_fraction"],
            }
            results.append(
                {
                    **who,
                    "qid": qid,
                    "label": label,
                    "claims_correct": f"{correct}/{total}",
                    "claims_missing": verdicts.count("missing"),
                    "claims_contradicted": contradicted,
                    "false_statements": false_statements,
                    "minor_inaccuracies": minor,
                    "core_lenient": s["core_lenient"],
                    "quote_verified": s["quote_verified"],
                    "callee_located": s["callee_located"],
                    "checks": checks,
                    "passed": all(checks.values()),
                }
            )
    results.sort(key=lambda r: (r["tier"], r["run"], r["qid"]))
    (grade / "results.json").write_text(json.dumps(results, indent=1), encoding="utf-8")
    for r in results:
        failed = [k for k, v in r["checks"].items() if not v]
        print(
            r["tier"], r["run"], r["qid"], "claims", r["claims_correct"],
            "contra", r["claims_contradicted"], "false", r["false_statements"],
            "core", r["core_lenient"], "PASS" if r["passed"] else f"FAIL {failed}",
        )


def main() -> None:
    mode, ladder, grade = sys.argv[1], Path(sys.argv[2]), Path(sys.argv[3])
    if mode == "bundle":
        bundle(ladder, grade)
    else:
        merge(ladder, grade, Path(sys.argv[4]))


if __name__ == "__main__":
    main()
