"""Issue #359: scoring for the evidence-selection diagnostic (protocol §4-§6).

Scoring reads only (a) the frozen selection records written by the runner,
(b) the expected-chains file after its hash is verified, and (c) for the P3
recheck, the callers' stored chunks and pinned source. It never feeds anything
back into selection (control C4).

Support categories (§5a.5), plus the owner's P3 category (2026-11-13):

- graph_and_source: callee reached through a graph edge used by the arm, and
  the witness delivered in a caller passage. For a `route` relationship the
  declared structural alternative (§4) also counts as graph support: the
  rule used the route's HANDLED_BY edge to the caller.
- source_only: witness delivered, callee not graph-discovered.
- unresolved: witness not delivered.
- unwarranted_disambiguation: the arm followed one dynamic-dispatch candidate
  from the caller without the configuring relationship being supported. An
  error, not support.
- source_valid_index_missing: the witness is not in the caller's stored text
  at all (P3); recorded separately, not as a selector miss. Not support.
"""

from __future__ import annotations

import builtins
import hashlib
import io
import itertools
import json
import keyword
import re
import tokenize
from collections.abc import Mapping
from pathlib import Path

SCORING_VERSION = "359-scoring.v1"
BUDGETS = (4096, 16384)
SUPPORTED = ("graph_and_source", "source_only")
CATEGORIES = SUPPORTED + (
    "unresolved",
    "unwarranted_disambiguation",
    "source_valid_index_missing",
)


def sha256_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def load_verified(path: Path, expected_sha256: str) -> dict:
    """Load a sealed or frozen JSON file only if its bytes match the hash
    posted on #359. Refuses on mismatch (§9.1 step 5)."""
    actual = sha256_file(path)
    if actual != expected_sha256.lower():
        raise SystemExit(
            f"sha256 mismatch for {path.name}: expected {expected_sha256}, got {actual}"
        )
    return json.loads(path.read_text(encoding="utf-8"))


def render_cost(label: str, text: str, first: bool) -> int:
    """assemble_context costing: `[Source: label]\\n` + text, UTF-8 bytes,
    plus a 2-byte separator before every passage but the first."""
    part = f"[Source: {label}]\n{text}" if label else text
    return len(part.encode("utf-8")) + (0 if first else 2)


# ----------------------------------------------------------------- witnesses


def witness_hit(rel: dict, chunk: dict) -> bool:
    return chunk.get("label") == rel["caller"] and bool(
        re.search(rel["witness_regex"], chunk.get("text", ""))
    )


def stored_text_has_witness(rel: dict, caller_chunks: list[dict]) -> bool:
    return any(
        re.search(rel["witness_regex"], c.get("text", "")) for c in caller_chunks
    )


def source_has_witness(rel: dict, file_text: str) -> dict:
    """P3: the witness regex at its recorded lines in the pinned source."""
    lines = file_text.splitlines()
    pat = re.compile(rel["witness_regex"])
    at = {
        n: bool(0 < n <= len(lines) and pat.search(lines[n - 1]))
        for n in rel.get("lines", [])
    }
    return {
        "at_recorded_lines": at,
        "anywhere_in_file": bool(pat.search(file_text)),
        "valid": bool(at) and all(at.values()),
    }


# ----------------------------------------------------------------- categories


def _edge_from(caller: str, target: str, edges: list[list[str]]) -> bool:
    return any(e[0] == caller and e[1] == target for e in edges)


def _structural_route(rel: dict, edges: list[list[str]]) -> bool:
    route = rel.get("route_node")
    return bool(route) and any(
        e[0] == route and e[1] == rel["caller"] and e[2] == "HANDLED_BY" for e in edges
    )


def categorize(
    rel: dict,
    delivered: list[dict],
    edges: list[list[str]],
    supported_ids: set[str],
    index_has_witness: bool | None,
) -> dict:
    """One relationship, one arm/unit/budget. `edges` = the arm's
    edges_used (plus the RI edge under E2E)."""
    delivered_hit = any(witness_hit(rel, c) for c in delivered)
    cls = rel["resolution_class"]
    graph = False
    basis = None
    if cls == "route" and _structural_route(rel, edges):
        graph, basis = True, "structural_handled_by"
    elif cls == "dynamic_dispatch":
        followed = [
            c
            for c in rel.get("dispatch_candidates", [])
            if _edge_from(rel["caller"], c, edges)
        ]
        if followed:
            if rel.get("configured_by") not in supported_ids:
                return {
                    "category": "unwarranted_disambiguation",
                    "followed_candidates": followed,
                    "witness_delivered": delivered_hit,
                }
            graph, basis = True, "dispatch_with_configuring_evidence"
    elif rel.get("callee") and _edge_from(rel["caller"], rel["callee"], edges):
        graph, basis = True, "edge"
    if graph and (delivered_hit or basis == "structural_handled_by"):
        cat = "graph_and_source"
    elif delivered_hit:
        cat = "source_only"
    elif index_has_witness is False:
        cat = "source_valid_index_missing"
    else:
        cat = "unresolved"
    return {"category": cat, "basis": basis, "witness_delivered": delivered_hit}


def _ordered(rels: list[dict]) -> list[dict]:
    """Dispatch relationships after the relationships that configure them."""
    return sorted(rels, key=lambda r: r["resolution_class"] == "dynamic_dispatch")


def score_delivery(
    rels: list[dict],
    delivered: list[dict],
    requested: list[dict],
    functions: list[str],
    edges: list[list[str]],
    index_has: Mapping[str, bool | None],
) -> dict:
    supported: set[str] = set()
    per = {}
    for rel in _ordered(rels):
        res = categorize(rel, delivered, edges, supported, index_has.get(rel["id"]))
        if res["category"] in SUPPORTED:
            supported.add(rel["id"])
        else:
            res["reason"] = unproven_reason(rel, res, requested, functions)
        per[rel["id"]] = res
    core = [r["id"] for r in rels if r["tier"] == "core"]
    supporting = [r["id"] for r in rels if r["tier"] != "core"]
    return {
        "relationships": {r["id"]: per[r["id"]] for r in rels},
        "core_supported": sum(1 for i in core if i in supported),
        "core_total": len(core),
        "supporting_supported": sum(1 for i in supporting if i in supported),
        "supporting_total": len(supporting),
        "sufficiency": "PASS" if core and all(i in supported for i in core) else "FAIL",
        "by_class_and_category": _tally(rels, per),
    }


def unproven_reason(
    rel: dict, res: dict, requested: list[dict], functions: list[str]
) -> str:
    if res["category"] == "source_valid_index_missing":
        return "index_missing"
    if res["category"] == "unwarranted_disambiguation":
        return "unwarranted_disambiguation"
    if rel["caller"] not in functions:
        return "not_discovered"
    if not any(witness_hit(rel, c) for c in requested):
        return "not_selected"
    return "cut_by_budget"


def _tally(rels: list[dict], per: dict) -> dict:
    out: dict = {}
    for r in rels:
        cls = out.setdefault(r["resolution_class"], {})
        cat = per[r["id"]]["category"]
        cls[cat] = cls.get(cat, 0) + 1
    return out


# ----------------------------------------------------------------- selection


def chain_functions(rels: list[dict]) -> set[str]:
    out = {r["caller"] for r in rels}
    for r in rels:
        callee = r.get("callee") or ""
        if "#" in callee or callee.endswith((".py", ".ts", ".js", ".rs", ".java")):
            out.add(callee)
        out.update(r.get("dispatch_candidates", []))
    return out


def selection_metrics(rels: list[dict], functions: list[str]) -> dict:
    chain = chain_functions(rels)
    pos = {f: i + 1 for i, f in enumerate(functions)}
    positions = {f: pos.get(f) for f in sorted(chain)}
    found = [p for p in positions.values() if p]
    last = max(found) if found else 0
    fan_out = sum(1 for f in functions[: max(last - 1, 0)] if f not in chain)
    return {"chain_positions": positions, "fan_out_before_last_chain_function": fan_out}


def survival_metrics(rels: list[dict], delivered: list[dict], used: int) -> dict:
    callers = {r["caller"] for r in rels}
    relevant = sum(
        render_cost(c["label"], c["text"], i == 0)
        for i, c in enumerate(delivered)
        if c["label"] in callers
    )
    return {
        "passages": len(delivered),
        "bytes": used,
        "relevant_bytes": relevant,
        "relevant_share": round(relevant / used, 4) if used else 0.0,
    }


def budget_attribution(small: dict, large: dict, s_surv: dict, l_surv: dict) -> dict:
    def ok(s):
        return {i for i, r in s["relationships"].items() if r["category"] in SUPPORTED}

    rel_gain = s_surv["relevant_bytes"], l_surv["relevant_bytes"]
    non_gain = (
        s_surv["bytes"] - s_surv["relevant_bytes"],
        l_surv["bytes"] - l_surv["relevant_bytes"],
    )
    return {
        "relationships_gained": sorted(ok(large) - ok(small)),
        "relationships_lost": sorted(ok(small) - ok(large)),
        "relevant_bytes_gained": rel_gain[1] - rel_gain[0],
        "non_relevant_bytes_gained": non_gain[1] - non_gain[0],
    }


# ----------------------------------------------------------------- oracle bound


def minimum_evidence_bound(  # noqa: C901 - exhaustive per-caller cover
    rels: list[dict], caller_chunks: dict[str, list[dict]], route_structural: bool
) -> dict:
    """ORACLE BOUND (labelled; not a selector result): the smallest-byte set
    of caller passages that covers every core witness under assemble_context
    costing. With `route_structural`, `route` relationships are taken as
    satisfied by the HANDLED_BY edge (§4) and need no passage."""
    need: dict[str, list[dict]] = {}
    for r in rels:
        if r["tier"] != "core":
            continue
        if route_structural and r["resolution_class"] == "route":
            continue
        need.setdefault(r["caller"], []).append(r)
    chosen, total, missing = [], 0, []
    for caller, rs in sorted(need.items()):
        chunks = caller_chunks.get(caller, [])
        useful = [
            c
            for c in chunks
            if any(re.search(r["witness_regex"], c["text"]) for r in rs)
        ]
        best = None
        for k in range(1, len(rs) + 1):
            for combo in itertools.combinations(useful, k):
                if all(
                    any(re.search(r["witness_regex"], c["text"]) for c in combo)
                    for r in rs
                ):
                    cost = sum(render_cost(caller, c["text"], False) for c in combo)
                    if best is None or cost < best[0]:
                        best = (cost, combo)
            if best:
                break
        if best is None:
            missing.extend(
                r["id"]
                for r in rs
                if not any(re.search(r["witness_regex"], c["text"]) for c in chunks)
            )
            continue
        total += best[0]
        chosen.extend(
            {"label": caller, "chunk_index": c.get("chunk_index")} for c in best[1]
        )
    if chosen:
        total -= 2  # no separator before the first passage
    return {
        "label": "ORACLE BOUND (uses ground truth; not a selector result)",
        "route_relationships_structural": route_structural,
        "passages": chosen,
        "bytes": total if not missing else None,
        "uncoverable": missing,
        "feasible_at": {str(b): (not missing and total <= b) for b in BUDGETS},
    }


# ----------------------------------------------------------------- C3 scan

# Words a generic rule legitimately uses. A ground-truth term in this set is
# reported as an allowed overlap, never silently dropped.
GENERIC_ALLOWED = frozenset(
    {
        "route",
        "routes",
        "handler",
        "handlers",
        "graph",
        "nodes",
        "edges",
        "chunks",
        "passages",
        "search",
        "service",
        "method",
        "match",
        "matches",
        "order",
        "entry",
        "calls",
        "caller",
        "text",
        "function",
        "functions",
        "string",
        "literal",
        "path",
        "paths",
        "depth",
    }
)


def _terms_from_regex(regex: str) -> set[str]:
    """Literal fragments of a witness regex: character classes and
    quantifiers become separators; escaped characters keep their literal
    meaning, so `router\\.post` stays one term."""
    plain = re.sub(r"\\[bBsSdDwW][*+?]?", " ", regex)  # classes, anchors
    plain = re.sub(r"(?<!\\)[()\[\]{}+*?^$|]", " ", plain)  # unescaped syntax
    plain = re.sub(r"\\(.)", r"\1", plain)  # escaped characters are literal
    return set(re.findall(r"[\w/.#<=>-]{4,}", plain))


def forbidden_terms(  # noqa: C901 - one pass over every term source
    chains: dict, questions: dict | None = None
) -> set[str]:
    terms: set[str] = set()
    for rels in chains["chains"].values():
        for r in rels:
            for cid in [
                r["caller"],
                r.get("callee") or "",
                *r.get("dispatch_candidates", []),
            ]:
                if not cid or " " in cid:
                    continue
                terms.add(cid)
                path, _, sym = cid.partition("#")
                if path and not path.startswith("route:"):
                    terms.add(path)
                if sym:
                    terms.add(sym)
                    terms.update(s for s in sym.split(".") if len(s) >= 4)
            if r.get("route_node"):
                terms.add(r["route_node"])
            terms.update(_terms_from_regex(r["witness_regex"]))
    for q in (questions or {}).get("questions", []):
        for _, path in re.findall(
            r"\b(GET|POST|PUT|DELETE|PATCH)\s+(/[\w/{}.-]*)", q["question"]
        ):
            p = path.rstrip("./")
            if len(p) > 1:
                terms.add(p)
        q_words = set(re.findall(r"[a-z]{5,}", q["question"].lower()))
        id_words = {
            w
            for t in terms
            for w in re.findall(
                r"[a-z]{5,}", re.sub(r"([a-z])([A-Z])", r"\1 \2", t).lower()
            )
        }
        terms.update(q_words & id_words)
    return {t for t in terms if len(t) >= 4}


# Names that are Python, not ground truth: keywords, builtins, and method
# names of the standard types the rules use (`.items()`, `.search(`).
_LANGUAGE_NAMES = frozenset(
    {*keyword.kwlist, *dir(builtins)}
    | {
        n
        for t in (str, dict, list, set, tuple, re.compile(""), re.match("", ""))
        for n in dir(t)
    }
)


def _module_surface(source: str) -> tuple[str, set[str]]:
    """(string literals and comments, identifiers written in the module).
    An identifier that follows a `.` and is a standard-type method name is
    language, not content, and is left out."""
    text, names, prev = [], set(), ""
    for tok in tokenize.generate_tokens(io.StringIO(source).readline):
        if tok.type in (tokenize.STRING, tokenize.COMMENT):
            text.append(tok.string)
        elif tok.type == tokenize.FSTRING_MIDDLE:
            text.append(tok.string)
        elif tok.type == tokenize.NAME:
            if not (prev == "." and tok.string in _LANGUAGE_NAMES):
                names.add(tok.string.lower())
        prev = tok.string
    return "\n".join(text), names


def c3_scan(module_source: str, terms: set[str]) -> dict:
    """C3: ground-truth terms in the selection module. Paths, IDs and other
    terms with punctuation are searched anywhere in the source. Plain words
    are searched in string literals and comments (word boundaries) and as
    whole identifiers, so a standard-library call such as `.items()` is not
    a hit for a ground-truth word `items`."""
    text, names = _module_surface(module_source)
    hits, allowed = [], []
    for t in sorted(terms):
        if re.fullmatch(r"\w+", t):
            found = t.lower() in names or re.search(
                rf"(?<![\w]){re.escape(t)}(?![\w])", text, re.IGNORECASE
            )
        else:
            found = t in module_source
        if found:
            (allowed if t.lower() in GENERIC_ALLOWED else hits).append(t)
    return {"hits": hits, "allowed_generic_overlap": allowed, "clean": not hits}
