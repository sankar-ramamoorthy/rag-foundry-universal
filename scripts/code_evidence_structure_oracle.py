"""Offline structural-context feasibility oracle for the frozen E1 cases (#276).

Question: can *source-faithful* statements, **including the enclosing structure
needed to read them correctly**, fit the fixed 4096-byte final context?

Oracle only. It knows the frozen witness expressions, which a query-time
selector does not, so a fit is a bound on feasibility, never retrieval success.
Nothing here selects evidence for a query, changes retrieval, or touches a
service. Every delivered line is copied verbatim from the pinned function body;
the only synthetic lines are explicit ``# ... lines A-B omitted`` markers.

Tiers, each a superset of the previous (bytes include labels and separators):

* T0b  witness statements only, one block per function with omission markers
* T1   + function signature (decorators) and the headers of every enclosing
       if/elif/else, loop, with, try/except/else/finally
* T2   + the nearest preceding local definition of every name the witnesses read
* T3   + the transitive closure of T2 (upper bound)

T2/T3 use "nearest preceding definition", which is NOT a sound reaching-definition
analysis (issue #254's separated investigations record the same limit). The
report therefore also lists names with several candidate definitions so the
uncertainty is visible instead of hidden.

A witness expression whose first line occurs more than once in its function is
ambiguous. Both readings are reported: ``first`` (what the merged #264 oracle
did) and ``all`` (every occurrence included, an upper bound).

    ./.venv/Scripts/python.exe scripts/code_evidence_structure_oracle.py [--json OUT]
"""

from __future__ import annotations

import argparse
import ast
import builtins
import json
import sys
import textwrap
from pathlib import Path
from typing import Any, Iterator

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

import code_evidence_feasibility as base  # noqa: E402

TIERS = ("T0b", "T1", "T2", "T3")
READINGS = ("first", "all")
BUILTINS = set(dir(builtins))
TRY_TYPES = tuple(t for t in (ast.Try, getattr(ast, "TryStar", None)) if t)
FUNC_TYPES = (ast.FunctionDef, ast.AsyncFunctionDef)
Site = tuple[int, list[int], str]  # (start line1, line indices, kind)


class FunctionStructure:
    """Line-level structure of one pinned function body (1-based AST lines)."""

    def __init__(self, text: str):
        self.lines = text.split("\n")
        self.failures: list[str] = []
        tree = ast.parse(textwrap.dedent(text))
        root = tree.body[0] if tree.body else None
        if not isinstance(root, FUNC_TYPES):
            raise ValueError("source is not a single function definition")
        self.root = root
        self.params = self._param_names()
        self.expr_local = self._expression_local_names()
        self.defs = self._definition_sites()

    # ------------------------------------------------------------ structure
    def _header(self, node: ast.AST, body: list[ast.stmt]) -> list[int]:
        decorators = getattr(node, "decorator_list", [])
        first_line = node.lineno  # type: ignore[attr-defined]
        start = (min(d.lineno for d in decorators) if decorators else first_line) - 1
        end = first_line - 1
        if body[0].lineno > first_line:
            end = body[0].lineno - 2
            while end > first_line - 1 and (
                not self.lines[end].strip() or self.lines[end].lstrip().startswith("#")
            ):
                end -= 1
        return list(range(start, end + 1))

    def _keyword_line(self, after1: int, before1: int, keyword: str) -> int | None:
        for k in range(after1, before1 - 1):
            if self.lines[k].lstrip().startswith(keyword):
                return k
        self.failures.append(f"{keyword}_line_not_found_between_{after1}_{before1}")
        return None

    @staticmethod
    def _child(stmts: list[ast.stmt], line1: int) -> ast.stmt | None:
        for s in stmts:
            if s.lineno <= line1 <= (s.end_lineno or s.lineno):
                return s
        return None

    @staticmethod
    def _add(cats: dict[int, str], idxs: list[int | None], kind: str) -> None:
        for i in idxs:
            if i is not None:
                cats.setdefault(i, kind)

    @staticmethod
    def _blocks(node: Any) -> list[list[ast.stmt]]:
        out = [v for attr in ("body", "orelse", "finalbody")
               if isinstance(v := getattr(node, attr, None), list)
               and v and isinstance(v[0], ast.stmt)]
        out += [h.body for h in getattr(node, "handlers", [])]
        return out

    def statement_span(self, line1: int) -> list[int]:
        """Line indices of the whole simple statement (or compound header)
        that contains ``line1``, so a witness found mid-expression is never
        delivered as an orphaned fragment."""
        node = self._child(self.root.body, line1)
        while node is not None:
            inner = next((c for b in self._blocks(node)
                          if (c := self._child(b, line1))), None)
            if inner is None:
                break
            node = inner
        if node is None:
            return [line1 - 1]
        if not self._blocks(node):
            return list(range(node.lineno - 1, node.end_lineno or node.lineno))
        for handler in getattr(node, "handlers", []):
            if handler.lineno <= line1 < handler.body[0].lineno:
                return self._header(handler, handler.body)
        if TRY_TYPES and isinstance(node, TRY_TYPES):
            return [line1 - 1]
        header = self._header(node, node.body)
        return header if header[0] < line1 <= header[-1] + 1 else [line1 - 1]

    def structure(self, line1: int) -> dict[int, str]:
        """Signature plus the headers every statement at ``line1`` depends on."""
        cats = dict.fromkeys(self._header(self.root, self.root.body), "signature")
        node = self._child(self.root.body, line1)
        while node is not None:
            node = self._descend(node, line1, cats)
        return cats

    def _descend(self, node: ast.stmt, line1: int, cats: dict[int, str]):
        if isinstance(node, (*FUNC_TYPES, ast.ClassDef)):
            return self._descend_block(node, line1, cats, "nested_def")
        if isinstance(node, ast.If):
            return self._descend_if(node, line1, cats)
        if isinstance(node, (ast.For, ast.AsyncFor, ast.While)):
            return self._descend_loop(node, line1, cats)
        if isinstance(node, (ast.With, ast.AsyncWith)):
            return self._descend_block(node, line1, cats, "with")
        if TRY_TYPES and isinstance(node, TRY_TYPES):
            return self._descend_try(node, line1, cats)
        if isinstance(node, ast.Match):
            self.failures.append(f"unsupported_match_at_line_{node.lineno}")
        return None

    def _descend_block(self, node: Any, line1: int, cats: dict[int, str], kind: str):
        if line1 < node.body[0].lineno:
            return None  # the witness is the header itself
        self._add(cats, self._header(node, node.body), kind)
        return self._child(node.body, line1)

    def _descend_loop(self, node: Any, line1: int, cats: dict[int, str]):
        if line1 < node.body[0].lineno:
            return None
        self._add(cats, self._header(node, node.body), "loop")
        if line1 <= (node.body[-1].end_lineno or 0):
            return self._child(node.body, line1)
        self._add(cats, [self._keyword_line(
            node.body[-1].end_lineno or 0, node.orelse[0].lineno, "else")], "else")
        return self._child(node.orelse, line1)

    def _descend_if(self, node: ast.If, line1: int, cats: dict[int, str]):
        if line1 < node.body[0].lineno:
            return None
        self._add(cats, self._header(node, node.body), "branch")
        if line1 <= (node.body[-1].end_lineno or 0):
            return self._child(node.body, line1)
        first = node.orelse[0]
        if (
            len(node.orelse) == 1
            and isinstance(first, ast.If)
            and self.lines[first.lineno - 1].lstrip().startswith("elif")
        ):
            return first  # earlier conditions stay; the elif adds its own header
        self._add(cats, [self._keyword_line(
            node.body[-1].end_lineno or 0, first.lineno, "else")], "else")
        return self._child(node.orelse, line1)

    def _descend_try(self, node: Any, line1: int, cats: dict[int, str]):
        self._add(cats, [node.lineno - 1], "try")
        if node.body[0].lineno <= line1 <= (node.body[-1].end_lineno or 0):
            return self._child(node.body, line1)
        handler = self._child_handler(node, line1)
        if handler is not None:
            if line1 < handler.body[0].lineno:
                return None
            self._add(cats, self._header(handler, handler.body), "except")
            return self._child(handler.body, line1)
        last_try = node.handlers[-1] if node.handlers else node.body[-1]
        if node.orelse and line1 <= (node.orelse[-1].end_lineno or 0):
            self._add(cats, [self._keyword_line(
                last_try.end_lineno or 0, node.orelse[0].lineno, "else")], "else")
            return self._child(node.orelse, line1)
        if node.finalbody:
            before = (node.orelse[-1] if node.orelse else last_try).end_lineno
            self._add(cats, [self._keyword_line(
                before or 0, node.finalbody[0].lineno, "finally")], "finally")
            return self._child(node.finalbody, line1)
        return None

    @staticmethod
    def _child_handler(node: Any, line1: int):
        for h in node.handlers:
            if h.lineno <= line1 <= (h.end_lineno or 0):
                return h
        return None

    # --------------------------------------------------------- definitions
    def _param_names(self) -> set[str]:
        a = self.root.args
        names = [x.arg for x in (*a.posonlyargs, *a.args, *a.kwonlyargs)]
        names += [x.arg for x in (a.vararg, a.kwarg) if x]
        return set(names)

    def _expression_local_names(self) -> set[str]:
        names: set[str] = set()
        for n in ast.walk(self.root):
            if isinstance(n, ast.comprehension):
                names |= self._stored(n.target)
            elif isinstance(n, ast.Lambda):
                names |= {x.arg for x in ast.walk(n.args) if isinstance(x, ast.arg)}
            elif isinstance(n, ast.NamedExpr):
                self.failures.append(f"walrus_not_modelled_line_{n.lineno}")
        return names

    @staticmethod
    def _stored(target: ast.AST) -> set[str]:
        return {x.id for x in ast.walk(target)
                if isinstance(x, ast.Name) and isinstance(x.ctx, ast.Store)}

    def _definition_sites(self) -> dict[str, list[Site]]:
        sites: dict[str, list[Site]] = {}
        for n in ast.walk(self.root):
            if n is not self.root:
                for name, site in self._sites_of(n):
                    sites.setdefault(name, []).append(site)
        return sites

    def _sites_of(self, n: ast.AST) -> Iterator[tuple[str, Site]]:
        if isinstance(n, (ast.Assign, ast.AugAssign, ast.AnnAssign)):
            yield from self._assign_sites(n)
        elif isinstance(n, (ast.For, ast.AsyncFor)):
            for name in self._stored(n.target):
                yield name, (n.lineno, self._header(n, n.body), "loop_var")
        elif isinstance(n, (ast.With, ast.AsyncWith)):
            yield from self._with_sites(n)
        elif isinstance(n, ast.ExceptHandler) and n.name:
            yield n.name, (n.lineno, self._header(n, n.body), "except_var")
        elif isinstance(n, (*FUNC_TYPES, ast.ClassDef)):
            yield n.name, (n.lineno, self._header(n, n.body), "nested_def")
        elif isinstance(n, (ast.Import, ast.ImportFrom)):
            for alias in n.names:
                name = (alias.asname or alias.name).split(".")[0]
                yield name, (n.lineno, [n.lineno - 1], "import")

    def _assign_sites(self, n: Any) -> Iterator[tuple[str, Site]]:
        targets = n.targets if isinstance(n, ast.Assign) else [n.target]
        span = list(range(n.lineno - 1, n.end_lineno or n.lineno))
        for t in targets:
            for name in self._stored(t):
                yield name, (n.lineno, span, "assign")

    def _with_sites(self, n: Any) -> Iterator[tuple[str, Site]]:
        for item in n.items:
            for name in self._stored(item.optional_vars or ast.Pass()):
                yield name, (n.lineno, self._header(n, n.body), "with_var")

    def reads(self, line_set1: set[int]) -> list[tuple[str, int]]:
        return sorted({
            (n.id, n.lineno) for n in ast.walk(self.root)
            if isinstance(n, ast.Name) and isinstance(n.ctx, ast.Load)
            and n.lineno in line_set1
        })


class DefinitionResolver:
    """Add nearest preceding definitions of names read by included statements.

    One hop unless ``closure``. Never mutates the caller's set of lines.
    """

    def __init__(self, fs: FunctionStructure, included: set[int], closure: bool):
        self.fs, self.included, self.closure = fs, included, closure
        self.added: dict[int, str] = {}
        self.report: dict[str, Any] = {
            "resolved": 0, "already_included": 0, "params": 0,
            "expression_local": 0, "external": [], "no_preceding_definition": [],
            "multiple_candidate_definitions": []}

    def run(self) -> tuple[dict[int, str], dict[str, Any]]:
        queue = self.fs.reads({i + 1 for i in self.included})
        seen: set[tuple[str, int]] = set()
        while queue:
            name, use = queue.pop()
            if (name, use) not in seen:
                seen.add((name, use))
                queue += self._resolve(name, use)
        for key in ("external", "no_preceding_definition",
                    "multiple_candidate_definitions"):
            self.report[key] = sorted(self.report[key])
        return self.added, self.report

    def _note(self, key: str, name: str) -> None:
        if name not in self.report[key]:
            self.report[key].append(name)

    def _resolve(self, name: str, use: int) -> list[tuple[str, int]]:
        fs = self.fs
        sites = [s for s in fs.defs.get(name, []) if s[0] < use]
        if name in fs.params and not sites:
            self.report["params"] += 1
        elif name in fs.expr_local and name not in fs.defs:
            self.report["expression_local"] += 1
        elif name not in fs.defs:
            if name not in BUILTINS:
                self._note("external", name)
        elif not sites:
            self._note("no_preceding_definition", name)
        else:
            return self._take(name, sites)
        return []

    def _take(self, name: str, sites: list[Site]) -> list[tuple[str, int]]:
        start, idxs, kind = max(sites, key=lambda s: s[0])
        if len({s[0] for s in sites}) > 1:
            self._note("multiple_candidate_definitions", name)
        if all(i in self.included or i in self.added for i in idxs):
            self.report["already_included"] += 1
            return []
        self.report["resolved"] += 1
        for i in idxs:
            if i not in self.included:
                self.added.setdefault(i, f"def:{kind}")
        for i, cat in self.fs.structure(start).items():
            if i not in self.included:
                self.added.setdefault(i, cat)
        return self.fs.reads({i + 1 for i in idxs}) if self.closure else []


def render_block(lines: list[str], idxs: list[int]) -> tuple[str, int, int]:
    """Verbatim lines in order with explicit omission markers.

    Returns (text, marker_count, marker_bytes). Gaps made only of blank lines
    are dropped without a marker; any omitted code gets one.
    """
    out: list[str] = []
    stats = [0, 0]  # markers, marker bytes

    def marker(first0: int, last0: int, indent_of: str) -> None:
        indent = indent_of[: len(indent_of) - len(indent_of.lstrip())]
        span = (f"line {first0 + 1}" if first0 == last0
                else f"lines {first0 + 1}-{last0 + 1}")
        text = f"{indent}# ... {span} omitted"
        out.append(text)
        stats[0] += 1
        stats[1] += base.utf8(text) + 1

    prev: int | None = None
    for i in idxs:
        if prev is not None and i > prev + 1:
            if any(lines[k].strip() for k in range(prev + 1, i)):
                marker(prev + 1, i - 1, lines[i])
        out.append(lines[i])
        prev = i
    if prev is not None and any(lines[k].strip() for k in range(prev + 1, len(lines))):
        marker(prev + 1, len(lines) - 1, lines[prev])
    return "\n".join(out), stats[0], stats[1]


def locate_all(lines: list[str], expr: str) -> list[int]:
    first = expr.split("\n")[0].strip()
    hits = [i for i, line in enumerate(lines) if first in line]
    if hits:
        return hits
    target = base.norm(expr)
    return [i for i in range(len(lines))
            if target in base.norm(" ".join(lines[i: i + 4]))]


def witness_lines(
    fs: FunctionStructure, items: list[str], reading: str
) -> tuple[set[int], list[str], list[str]]:
    """Whole-statement line indices for the frozen expressions.

    Returns (indices, failures, ambiguities). ``reading`` is ``first`` or ``all``.
    """
    lines = fs.lines
    covered: set[int] = set()
    failures: list[str] = []
    ambiguous: list[str] = []
    for expr in items:
        hits = locate_all(lines, expr)
        if not hits:
            failures.append(f"unlocated:{expr[:50]}")
            continue
        if len(hits) > 1:
            ambiguous.append(f"{len(hits)}x:{expr.split(chr(10))[0].strip()[:50]}")
        for i in (hits if reading == "all" else hits[:1]):
            covered.update(fs.statement_span(i + 1))
    return covered, failures, ambiguous


def tier_sets(fs: FunctionStructure, witness: set[int]):
    structure: dict[int, str] = {}
    for line0 in sorted(witness):
        structure.update(fs.structure(line0 + 1))
    t1 = witness | set(structure)
    added2, rep2 = DefinitionResolver(fs, t1, closure=False).run()
    added3, rep3 = DefinitionResolver(fs, t1, closure=True).run()
    sets = {"T0b": witness, "T1": t1, "T2": t1 | set(added2), "T3": t1 | set(added3)}
    return sets, structure, (added2, rep2), (added3, rep3)


def category_bytes(fs: FunctionStructure, idxs: set[int], witness: set[int],
                   structure: dict[int, str]) -> dict[str, int]:
    """Bytes of the verbatim lines by role (excludes markers, labels)."""
    out: dict[str, int] = {}
    for i in idxs:
        if i in witness:
            role = "witness"
        elif i in structure:
            role = "signature" if structure[i] == "signature" else "structure"
        else:
            role = "definitions"
        out[role] = out.get(role, 0) + base.utf8(fs.lines[i]) + 1
    return dict(sorted(out.items()))


def evaluate_document(cid: str, text: str, items: list[str], reading: str):
    fs = FunctionStructure(text)
    witness, failures, ambiguous = witness_lines(fs, items, reading)
    sets, structure, (added2, rep2), (added3, rep3) = tier_sets(fs, witness)
    parts: dict[str, tuple[str, str]] = {}
    tiers: dict[str, Any] = {}
    for tier, idxs in sets.items():
        ordered = sorted(idxs)
        block, markers, marker_bytes = render_block(fs.lines, ordered)
        parts[tier] = (f"{cid} [lines {ordered[0] + 1}-{ordered[-1] + 1}]", block)
        tiers[tier] = {"lines_included": len(ordered), "omission_markers": markers,
                       "marker_bytes": marker_bytes, "block_bytes": base.utf8(block),
                       "bytes_by_category": category_bytes(fs, idxs, witness,
                                                           structure)}
    detail = {
        "source_lines": len(fs.lines), "witness_lines": len(witness),
        "ambiguous_expressions": ambiguous, "tiers": tiers,
        "structure_lines_by_kind": _count(
            [v for i, v in structure.items() if i not in witness]),
        "definition_lines_added_T2": len(added2),
        "definition_lines_added_T3": len(added3),
        "dependencies_T2": rep2, "dependencies_T3": rep3,
    }
    return parts, detail, failures + [f"struct:{f}" for f in fs.failures]


def evaluate_case(case: dict, manifest: dict, reading: str) -> dict:
    cap = manifest["context_cap_bytes"]
    by_doc: dict[str, list[str]] = {}
    for group in (case["operations"], case["dependencies"]):
        for w in group:
            by_doc.setdefault(w["canonical_id"], []).extend(w["expressions"])
    per_tier: dict[str, list[tuple[str, str]]] = {t: [] for t in TIERS}
    documents: dict[str, Any] = {}
    failures: list[str] = []
    for cid, items in by_doc.items():
        try:
            parts, detail, problems = evaluate_document(
                cid, manifest["sources"][cid]["text"], items, reading)
        except (SyntaxError, ValueError) as err:
            failures.append(f"{cid}:parse_failed:{err}")
            continue
        for tier in TIERS:
            per_tier[tier].append(parts[tier])
        documents[cid] = detail
        failures += [f"{cid}:{p}" for p in problems]
    tiers = {}
    for tier, plist in per_tier.items():
        total = base.context_bytes(plist)
        block_bytes = sum(base.utf8(block) for _, block in plist)
        tiers[tier] = {"bytes": total, "slack": cap - total, "fits": total <= cap,
                       "blocks": len(plist),
                       "labels_and_separators_bytes": total - block_bytes}
    return {"tiers": tiers, "documents": documents, "failures": failures}


def _count(items: list[str]) -> dict[str, int]:
    out: dict[str, int] = {}
    for item in items:
        out[item] = out.get(item, 0) + 1
    return dict(sorted(out.items()))


def run() -> dict:
    manifest = json.loads(base.MANIFEST.read_text(encoding="utf-8"))
    return {
        "cap_bytes": manifest["context_cap_bytes"],
        "oracle_notice": "Oracle-selected evidence: bounds feasibility only.",
        "cases": {
            c["id"]: {r: evaluate_case(c, manifest, r) for r in READINGS}
            for c in manifest["cases"]
        },
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--json", type=Path, help="write full results JSON here")
    args = parser.parse_args()
    out = run()
    print(f"cap={out['cap_bytes']}  cells are bytes/slack, * = over the cap")
    for reading in READINGS:
        print(f"\nreading={reading}")
        print("case " + "".join(f"{t:>16}" for t in TIERS) + "  failures")
        for cid, r in out["cases"].items():
            cells = ""
            for t in TIERS:
                x = r[reading]["tiers"][t]
                flag = "*" if not x["fits"] else " "
                cells += f"{x['bytes']:>9}/{x['slack']:<5}{flag}"
            print(f"{cid:4} {cells}  {len(r[reading]['failures'])}")
    if args.json:
        args.json.write_text(json.dumps(out, indent=2), encoding="utf-8")


if __name__ == "__main__":
    main()
