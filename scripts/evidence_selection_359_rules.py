"""Issue #359: the frozen, generic selection rules (protocol §5, §5a, §5b).

This module holds only the rules: route identification (Stage RI), the
traversal arms G0-G3, and the passage units P-whole / P-call. It performs no
I/O; the runner passes in the exported graph, the deployed /trace hops and a
function that returns a node's stored chunks.

Control C3: this module must not import the ground truth or the scoring
module, and must not contain any ground-truth canonical ID, symbol name, file
path or question-specific term. `tests/test_evidence_selection_359.py` scans
it. Allowed signals: the parsed route, edge types, call-site lines, chunk text
matched against names taken from graph edges, and string literals matched
against existing route nodes.

Where the frozen text leaves a detail open, the reading used is fixed in
INTERPRETATIONS before any run, disclosed in the harness PR, and copied into
every raw record.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Callable, Iterable

RULES_VERSION = "359-rules.v1"

ROUTE_IN_QUESTION = re.compile(r"\b(GET|POST|PUT|DELETE|PATCH)\s+(/[\w/{}.-]*)")
SUPPRESSED_PREFIXES = ("EXTERNAL_", "route:", "compose:")
MAX_DEPTH = 6  # server TRACE_MAX_DEPTH
MAX_NODES = 300  # server TRACE_MAX_NODES
ARMS = ("G0", "G1", "G2", "G3")
UNITS = ("P-whole", "P-call")

INTERPRETATIONS = {
    "route_mentions": (
        "Every METHOD /path mention in the question is matched; the union of "
        "matching route nodes must have exactly one member. A trailing '.' or "
        "'/' captured from prose is stripped."
    ),
    "unresolved_vs_no_route_node": (
        "With zero matches, the code is unresolved_route when some route node "
        "with the same method has a router-local path that is a proper suffix "
        "of the question path (unresolved prefix, 5a.6), otherwise "
        "no_route_node. The suffix candidates are recorded; they are never "
        "used as an entry point."
    ),
    "handler": (
        "handler_missing when the route node has no HANDLED_BY target that is "
        "a real node; ambiguous_route when it has more than one."
    ),
    "node_cap": (
        "MAX_NODES counts every discovered node including the entry handler; "
        "discovery stops when the cap is reached and cap_hit is recorded."
    ),
    "depth": (
        "The entry handler is depth 0; nodes at depth MAX_DEPTH are discovered "
        "but not expanded."
    ),
    "visited": (
        "Each node is discovered once, at its first encounter in the arm's "
        "order (BFS for G1, DFS pre-order for G2/G3)."
    ),
    "ambiguous_call": (
        "Two or more real CALL targets of one caller that share a simple name "
        "and a call-site line form one ambiguous call site: none is followed, "
        "and the candidate set is recorded (5a.2)."
    ),
    "url_literal": (
        "G3 string literals are the contents of single-line quoted strings in "
        "the function's stored text; for f-strings each literal segment "
        "between replacement fields is a separate literal (as in Python's "
        "AST). A literal must equal a route node's path exactly; route node "
        "path = the part of `route:<service>:<METHOD>:<path>` after METHOD."
    ),
    "url_literal_position": (
        "Node metadata carries no line numbers, so a URL-literal route handler "
        "is added after the function's CALL children (at that function)."
    ),
    "p_call_children": (
        "P-call child names come from the function's CALL edges whose targets "
        "the arm selected; the simple name is the last dotted part of the "
        "symbol (or the file stem for a module node)."
    ),
    "g0": (
        "G0 takes the deployed /trace hops (start = entry handler, "
        "relation_types HANDLED_BY,CALL, forward) in hop order and keeps "
        "nodes without a suppressed prefix."
    ),
}


# ----------------------------------------------------------------- graph


@dataclass(frozen=True)
class Edge:
    to: str
    rel: str
    lines: tuple[int, ...] = ()


@dataclass
class Graph:
    nodes: set[str] = field(default_factory=set)
    out: dict[str, list[Edge]] = field(default_factory=dict)

    def edges(self, frm: str, rel: str) -> list[Edge]:
        return [e for e in self.out.get(frm, []) if e.rel == rel]


def graph_from_export(data: dict) -> Graph:
    """Build from `GET /v1/graph/repos/{id}` (nodes list; relationships
    keyed by source canonical ID; CALL metadata `call_sites` = line numbers)."""
    graph = Graph(nodes={n["canonical_id"] for n in data["nodes"]})
    for frm, edges in data["relationships"].items():
        for e in edges:
            meta = e.get("relationship_metadata") or {}
            lines = meta.get("call_sites") or ()
            graph.out.setdefault(frm, []).append(
                Edge(
                    e["to_canonical_id"],
                    e["relation_type"],
                    tuple(int(x) for x in lines if isinstance(x, int)),
                )
            )
    return graph


def is_suppressed(cid: str) -> bool:
    return cid.startswith(SUPPRESSED_PREFIXES)


def simple_name(cid: str) -> str:
    if "#" in cid:
        return cid.split("#", 1)[1].rsplit(".", 1)[-1]
    stem = cid.rsplit("/", 1)[-1]
    return stem.rsplit(".", 1)[0]


def route_path(route_cid: str) -> str | None:
    parts = route_cid.split(":", 3)
    return parts[3] if len(parts) == 4 and parts[0] == "route" else None


def route_method(route_cid: str) -> str | None:
    parts = route_cid.split(":", 3)
    return parts[2] if len(parts) == 4 and parts[0] == "route" else None


# ----------------------------------------------------------------- Stage RI


def identify_route(question: str, graph: Graph) -> dict:
    """Stage RI (§5, §5b). Uses only the question text and the graph."""
    mentions = []
    for method, raw in ROUTE_IN_QUESTION.findall(question):
        path = raw.rstrip("./") or "/"
        mentions.append((method, path))
    routes = sorted(c for c in graph.nodes if c.startswith("route:"))
    matches = sorted(
        {r for m, p in mentions for r in routes if r.endswith(f":{m}:{p}")}
    )
    result = {
        "mentions": [f"{m} {p}" for m, p in mentions],
        "route_matches": matches,
        "route_node": None,
        "handler": None,
        "edges_used": [],
        "suffix_candidates": [],
    }
    if len(matches) > 1:
        return {**result, "code": "ambiguous_route"}
    if not matches:
        suffix = sorted(
            r
            for m, p in mentions
            for r in routes
            if route_method(r) == m
            and (rp := route_path(r))
            and rp != p
            and len(rp) > 1
            and p.endswith(rp)
        )
        code = "unresolved_route" if suffix else "no_route_node"
        return {**result, "code": code, "suffix_candidates": suffix}
    route = matches[0]
    handlers = sorted(
        e.to for e in graph.edges(route, "HANDLED_BY") if e.to in graph.nodes
    )
    if not handlers:
        return {**result, "code": "handler_missing", "route_node": route}
    if len(handlers) > 1:
        return {
            **result,
            "code": "ambiguous_route",
            "route_node": route,
            "handler_candidates": handlers,
        }
    return {
        **result,
        "code": "resolved",
        "route_node": route,
        "handler": handlers[0],
        "edges_used": [[route, handlers[0], "HANDLED_BY"]],
    }


# ----------------------------------------------------------------- traversal


def ordered_children(graph: Graph, frm: str) -> tuple[list[Edge], list[str], list]:
    """Real CALL children in call-site order; suppressed targets; ambiguous
    call sites (5a.2)."""
    real, suppressed = [], []
    for e in graph.edges(frm, "CALL"):
        if is_suppressed(e.to) or e.to not in graph.nodes:
            suppressed.append(e.to)
        else:
            real.append(e)
    ambiguous, excluded = [], set()
    by_name: dict[str, list[Edge]] = {}
    for e in real:
        by_name.setdefault(simple_name(e.to), []).append(e)
    for name, group in sorted(by_name.items()):
        for i, a in enumerate(group):
            clash = [b for b in group[i + 1 :] if set(a.lines) & set(b.lines)]
            if clash:
                cands = sorted({a.to, *(b.to for b in clash)})
                ambiguous.append({"caller": frm, "name": name, "candidates": cands})
                excluded.update(cands)
    real = [e for e in real if e.to not in excluded]
    real.sort(key=lambda e: (min(e.lines) if e.lines else 10**9, e.to))
    return real, sorted(suppressed), ambiguous


STRING_LITERAL = re.compile(
    r"""(?P<prefix>[rRbBuUfF]{0,2})(?P<q>["'])(?P<body>(?:\\.|(?!(?P=q)).)*?)(?P=q)"""
)
FSTRING_FIELD = re.compile(r"\{[^{}]*\}")


def string_literals(text: str) -> list[str]:
    out = []
    for line in text.splitlines():
        for m in STRING_LITERAL.finditer(line):
            body = m.group("body")
            if "f" in m.group("prefix").lower():
                out.extend(s for s in FSTRING_FIELD.split(body) if s)
            elif body:
                out.append(body)
    return out


def url_literal_routes(graph: Graph, text: str) -> tuple[list[dict], list[dict]]:
    """(matches, ambiguous): literals equal to exactly one / several route
    node paths."""
    by_path: dict[str, list[str]] = {}
    for c in graph.nodes:
        p = route_path(c)
        if p:
            by_path.setdefault(p, []).append(c)
    matches, ambiguous, seen = [], [], set()
    for lit in string_literals(text):
        if lit in seen or lit not in by_path:
            continue
        seen.add(lit)
        routes = sorted(by_path[lit])
        if len(routes) == 1:
            matches.append({"literal": lit, "route": routes[0]})
        else:
            ambiguous.append({"literal": lit, "candidates": routes})
    return matches, ambiguous


TextOf = Callable[[str], str]


def traverse(  # noqa: C901 - the frozen G1/G2/G3 rules kept in one place
    graph: Graph,
    entry: str,
    arm: str,
    text_of: TextOf | None = None,
    max_depth: int = MAX_DEPTH,
    max_nodes: int = MAX_NODES,
) -> dict:
    """G1 (BFS), G2 (DFS pre-order) or G3 (G2 + URL-literal route hop)."""
    if arm not in ("G1", "G2", "G3"):
        raise ValueError(arm)
    if arm == "G3" and text_of is None:
        raise ValueError("G3 needs stored text")
    order: list[str] = [entry]
    seen = {entry}
    edges_used: list[list[str]] = []
    suppressed: list[list[str]] = []
    ambiguous: list[dict] = []
    literal_hops: list[dict] = []
    cap_hit = False

    def kids(fn: str) -> list[str]:
        real, sup, amb = ordered_children(graph, fn)
        suppressed.extend([fn, s] for s in sup)
        ambiguous.extend(amb)
        out = []
        for e in real:
            edges_used.append([fn, e.to, "CALL"])
            out.append(e.to)
        if arm == "G3":
            assert text_of is not None
            hits, amb_lit = url_literal_routes(graph, text_of(fn))
            ambiguous.extend({"caller": fn, **a} for a in amb_lit)
            for h in hits:
                handlers = sorted(
                    e.to
                    for e in graph.edges(h["route"], "HANDLED_BY")
                    if e.to in graph.nodes
                )
                if len(handlers) != 1:
                    ambiguous.append(
                        {"caller": fn, **h, "handler_candidates": handlers}
                    )
                    continue
                edges_used.append([fn, h["route"], "URL_LITERAL"])
                edges_used.append([h["route"], handlers[0], "HANDLED_BY"])
                literal_hops.append({"caller": fn, **h, "handler": handlers[0]})
                out.append(handlers[0])
        return out

    if arm == "G1":
        frontier = [(entry, 0)]
        while frontier and not cap_hit:
            nxt = []
            for fn, d in frontier:
                if d >= max_depth:
                    continue
                for c in kids(fn):
                    if c in seen:
                        continue
                    if len(order) >= max_nodes:
                        cap_hit = True
                        break
                    seen.add(c)
                    order.append(c)
                    nxt.append((c, d + 1))
                if cap_hit:
                    break
            frontier = nxt
    else:

        def dfs(fn: str, d: int) -> None:
            nonlocal cap_hit
            if d >= max_depth or cap_hit:
                return
            for c in kids(fn):
                if cap_hit:
                    return
                if c in seen:
                    continue
                if len(order) >= max_nodes:
                    cap_hit = True
                    return
                seen.add(c)
                order.append(c)
                dfs(c, d + 1)

        dfs(entry, 0)

    return {
        "arm": arm,
        "entry": entry,
        "functions": order,
        "edges_used": edges_used,
        "suppressed": suppressed,
        "suppressed_count": len(suppressed),
        "ambiguous": ambiguous,
        "literal_hops": literal_hops,
        "cap_hit": cap_hit,
    }


def from_trace(graph: Graph, entry: str, hops: Iterable[dict], truncated) -> dict:
    """G0: the deployed /trace hop order, resolved nodes only."""
    order = [entry]
    edges_used, suppressed = [], []
    for h in hops:
        cid, parent, rel = (
            h["canonical_id"],
            h["parent_canonical_id"],
            h["relation_type"],
        )
        if is_suppressed(cid) or cid not in graph.nodes:
            suppressed.append([parent, cid])
            continue
        edges_used.append([parent, cid, rel])
        if cid not in order:
            order.append(cid)
    return {
        "arm": "G0",
        "entry": entry,
        "functions": order,
        "edges_used": edges_used,
        "suppressed": suppressed,
        "suppressed_count": len(suppressed),
        "ambiguous": [],
        "literal_hops": [],
        "cap_hit": bool(truncated),
    }


# ----------------------------------------------------------------- passages


def call_pattern(name: str) -> re.Pattern:
    return re.compile(rf"\b{re.escape(name)}\(")


def passages(
    graph: Graph,
    discovery: dict,
    unit: str,
    chunks_of: Callable[[str], list[dict]],
) -> list[dict]:
    """Passages in function-selection order, then chunk order (§5)."""
    selected = set(discovery["functions"])
    literals: dict[str, list[str]] = {}
    for h in discovery["literal_hops"]:
        literals.setdefault(h["caller"], []).append(h["literal"])
    out = []
    for fn in discovery["functions"]:
        chunks = chunks_of(fn)
        if unit == "P-whole":
            keep = chunks
        elif unit == "P-call":
            names = sorted(
                {
                    simple_name(e.to)
                    for e in graph.edges(fn, "CALL")
                    if e.to in selected and e.to != fn
                }
            )
            pats = [call_pattern(n) for n in names]
            lits = literals.get(fn, [])
            keep = [
                c
                for i, c in enumerate(chunks)
                if i == 0
                or any(p.search(str(c.get("text", ""))) for p in pats)
                or any(lit in str(c.get("text", "")) for lit in lits)
            ]
        else:
            raise ValueError(unit)
        out.extend(keep)
    return out
