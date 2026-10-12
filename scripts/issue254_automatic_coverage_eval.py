"""Offline query-seeded AST slicing spike, never imported by retrieval code.

Selection sees only question and pinned Python source, not oracle ranges or
coverage labels. Scoring is performed separately after freezing the output.
"""

import argparse
import ast
import json
import re
from pathlib import Path

from issue254_complete_evidence_eval import BUDGET, digest


def terms(text):
    return {part.lower().removesuffix("s") for part in
            re.findall(r"[A-Z]?[a-z]+|[A-Z]+(?![a-z])", text)}


def identifiers(node):
    return {child.id for child in ast.walk(node) if isinstance(child, ast.Name)}


def functions(tree):
    result = {}
    for node in tree.body:
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            result[node.name] = node
        elif isinstance(node, ast.ClassDef):
            for child in node.body:
                if isinstance(child, (ast.FunctionDef, ast.AsyncFunctionDef)):
                    result[f"{node.name}.{child.name}"] = child
    return result


def units(function):
    result = []

    def visit(node, headers):
        if not isinstance(node, ast.stmt):
            return
        nested = [child for child in ast.iter_child_nodes(node)
                  if isinstance(child, ast.stmt)]
        if nested:
            # Keep literal control headers along with selected leaf statements.
            first_body = min(child.lineno for child in nested)
            header = set(range(node.lineno, first_body))
            for child in nested:
                visit(child, headers | header)
        elif not (isinstance(node, ast.Expr)
                  and isinstance(node.value, ast.Constant)
                  and isinstance(node.value.value, str)):
            result.append((node, headers | set(
                range(node.lineno, (node.end_lineno or node.lineno) + 1))))

    for child in function.body:
        visit(child, set())
    return result


def render(sources, selected):
    parts, manifest = [], []
    for canonical, numbers in selected.items():
        path = canonical.split("#")[0]
        lines = sources[path]["text"].splitlines()
        ranges = []
        for number in sorted(numbers):
            if ranges and number == ranges[-1][1] + 1:
                ranges[-1][1] = number
            else:
                ranges.append([number, number])
        for first, last in ranges:
            text = "\n".join(lines[first - 1:last])
            parts.append(f"[Source: {canonical}]\n{text}")
            manifest.append({"canonical_id": canonical, "first_line": first,
                             "last_line": last, "text": text,
                             "text_sha256": digest(text),
                             "source_sha256": digest(sources[path]["text"])})
    return "\n\n".join(parts), manifest


def select(sources, question, budget=BUDGET):
    targets = re.findall(r"`([^`]+\.py#[^`]+)`", question)
    vocabulary = terms(re.sub(r"`[^`]+`", "", question))
    candidates = []
    for canonical in targets:
        path, symbol = canonical.split("#")
        function = functions(ast.parse(sources[path]["text"]))[symbol]
        items = units(function)
        for index, (node, lines) in enumerate(items):
            names = identifiers(node)
            attributes = {c.attr for c in ast.walk(node)
                          if isinstance(c, ast.Attribute)}
            overlap = len(terms(" ".join(names | attributes)) & vocabulary)
            if not overlap:
                continue
            closure = set(lines)
            pending = set(names) - {"self"}
            # Backward local def-use closure, nearest preceding definition.
            for preceding, previous_lines in reversed(items[:index]):
                assigned = {c.id for c in ast.walk(preceding)
                            if isinstance(c, ast.Name)
                            and isinstance(c.ctx, ast.Store)}
                if assigned & pending:
                    closure |= previous_lines
                    pending -= assigned
                    pending |= identifiers(preceding) - assigned - {"self"}
            candidates.append({"canonical": canonical, "lines": closure,
                               "utility": overlap,
                               "seed_line": node.lineno})
    selected = dict.fromkeys(targets)
    selected = {key: set() for key in selected}
    accepted, rejected = [], []
    while candidates:
        options = []
        current, _ = render(sources, selected)
        current_bytes = len(current.encode())
        for item in candidates:
            trial = {key: set(value) for key, value in selected.items()}
            trial[item["canonical"]] |= item["lines"]
            evidence, _ = render(sources, trial)
            cost = len(evidence.encode())
            marginal = max(1, cost - current_bytes)
            # Cover explicitly named owners before adding detail to one owner.
            priority = 2 if not selected[item["canonical"]] else 1
            options.append((priority, item["utility"] / marginal,
                            -item["seed_line"], item, trial, cost))
        best = max(options, key=lambda option: option[:3])
        _, _, _, item, trial, cost = best
        candidates.remove(item)
        record = {key: value for key, value in item.items() if key != "lines"}
        record["trial_bytes"] = cost
        if cost <= budget:
            selected = trial
            accepted.append(record)
        else:
            rejected.append(record)
    evidence, manifest = render(sources, selected)
    return {"evidence": evidence, "evidence_bytes": len(evidence.encode()),
            "manifest": manifest, "accepted_seeds": accepted,
            "budget_rejected_seeds": rejected,
            "unresolved_dependencies": "Attribute state and external callable "
                                       "initializers are not resolved by this spike"}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--source-context", type=Path, required=True)
    parser.add_argument("--experiment", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if args.output.exists():
        raise SystemExit("Refusing to overwrite a frozen selection")
    sources = json.loads(args.source_context.read_text(encoding="utf-8"))[
        "pinned_source"]
    experiment = json.loads(args.experiment.read_text(encoding="utf-8"))
    question = experiment["payloads"]["complete_evidence"]["query"]
    result = {
        "protocol": "query lexical overlap + nearest local definition closure; "
                    "named-owner priority + marginal UTF-8 byte utility; literal "
                    "AST statement/header spans; no oracle inputs to selector",
        "scope": "Offline full pinned source pool, not the live k=3 chunk pool; "
                 "no automatic source acquisition or production claim",
        "selector_sha256": digest(Path(__file__).read_text(encoding="utf-8")),
        "pin": experiment["pin"], "question": question, "budget": BUDGET,
        "selection": select(sources, question),
    }
    args.output.write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    print(result["selection"]["evidence_bytes"], "bytes")


if __name__ == "__main__":
    main()
