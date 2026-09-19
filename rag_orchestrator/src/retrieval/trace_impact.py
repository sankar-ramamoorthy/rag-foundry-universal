# rag_orchestrator/src/retrieval/trace_impact.py
"""
TRACE / IMPACT bounded structural query modes (issue #198).

Pure functions over the existing in-memory `CodebaseGraph`/`Node`
(`codebase_queries.py`) -- no changes to that module, no DB/HTTP access
here. Both modes are computed fresh per query from the already-cached
full-repo graph (`codebase_utils.get_cached_graph`); nothing here is
persisted, unlike #197's ingestion-time ORIENT facts.

TRACE: an ordered path with per-hop evidence (canonical_id, relation_type,
parent) from a resolved starting symbol -- not just a bag of connected
nodes like `bfs_traversal` returns.

IMPACT: a candidate-affected-set (reverse CALL/IMPORTS/INHERITS/OVERRIDES)
with each candidate's basis for inclusion -- explicitly a candidate set,
never a claim that a candidate will actually break.

Both are bounded: an unresolvable or ambiguous starting symbol fails
clearly (see `resolve_start_symbol`), and exceeding the configured
node/candidate budget stops computation outright (`truncated=True`) --
no unbounded pass is ever performed to report how much *more* graph
exists past that point.
"""

from collections import deque
from dataclasses import dataclass, field

from src.retrieval.codebase_queries import CodebaseGraph, Node

# CALL/IMPORTS/INHERITS/OVERRIDES are "affected by a change" relations;
# DEFINES (structural containment) and DOCUMENTS (doc-to-code links) are
# deliberately excluded -- neither represents something being affected by
# a change to the start symbol.
IMPACT_RELATION_TYPES = ("CALL", "IMPORTS", "INHERITS", "OVERRIDES")

_EXTERNAL_PREFIXES = ("EXTERNAL_MODULE:", "EXTERNAL_SYMBOL:")


@dataclass(frozen=True)
class ResolvedStart:
    canonical_id: str
    file_path: str


@dataclass(frozen=True)
class AmbiguousStart:
    query: str
    candidates: list[str]  # every canonical_id whose trailing symbol matches, sorted


@dataclass(frozen=True)
class Hop:
    canonical_id: str
    file_path: str
    hop_index: int  # BFS depth from the resolved start, 1-indexed
    relation_type: str
    parent_canonical_id: str
    # Issue #220: confidence/call_sites/bases/etc, when the underlying
    # edge carried relationship_metadata (CALL/IMPORTS/INHERITS all do;
    # DEFINES never does). {} when nothing was recorded for this edge --
    # absence of evidence, not evidence of a weak edge.
    metadata: dict = field(default_factory=dict)


@dataclass(frozen=True)
class GapNote:
    canonical_id: str
    reason: str


@dataclass(frozen=True)
class TraceResult:
    resolved_start: ResolvedStart
    relation_types: list[str]
    direction: str
    max_depth: int
    hops: list[Hop]
    truncated: bool
    gaps: list[GapNote]


@dataclass(frozen=True)
class ImpactBasis:
    relation_type: str
    hop_distance: int
    path: list[str]  # canonical_ids, start -> candidate
    # Issue #220: the metadata of the single edge one hop away from the
    # candidate along `path` (i.e. the edge that most directly connects
    # this candidate to the rest of the path) -- not the whole path's
    # evidence, just this basis's own immediate edge.
    metadata: dict = field(default_factory=dict)


@dataclass(frozen=True)
class ImpactCandidate:
    canonical_id: str
    file_path: str
    basis: list[ImpactBasis]


@dataclass(frozen=True)
class ImpactResult:
    resolved_start: ResolvedStart
    relation_types_considered: list[str]
    max_depth: int
    candidates: list[ImpactCandidate]
    truncated: bool


def resolve_start_symbol(
    graph: CodebaseGraph, start: str
) -> ResolvedStart | AmbiguousStart | None:
    """Resolve a caller-supplied `start` (an exact canonical_id or a bare
    symbol name) to exactly one node.

    Deliberately stricter than `SymbolTable.lookup`'s existing
    lexicographically-smallest-wins convention (ADR-048): that convention
    is fine for a best-effort doc-to-code citation, but silently picking
    one of several same-named symbols here would produce a TRACE/IMPACT
    result that *looks* structurally authoritative -- the traversal
    itself is fully deterministic -- while possibly tracing the wrong
    symbol entirely. An ambiguous bare name is reported, never guessed.
    """
    exact = graph.get_node(start)
    if exact is not None:
        return ResolvedStart(canonical_id=exact.canonical_id, file_path=exact.file_path)

    matches: set[str] = set()
    for canonical_id in graph.nodes:
        if "#" not in canonical_id:
            continue  # bare-name lookup only targets symbol-level nodes
        symbol_path = canonical_id.split("#", 1)[1]
        if symbol_path == start or symbol_path.rsplit(".", 1)[-1] == start:
            matches.add(canonical_id)

    if not matches:
        return None
    if len(matches) == 1:
        (canonical_id,) = matches
        node = graph.get_node(canonical_id)
        assert node is not None  # came from graph.nodes itself
        return ResolvedStart(canonical_id=node.canonical_id, file_path=node.file_path)
    return AmbiguousStart(query=start, candidates=sorted(matches))


def _record_hop(
    graph: CodebaseGraph,
    neighbor: Node,
    relation_type: str,
    parent: Node,
    new_depth: int,
    direction: str,
    hops: list[Hop],
    gaps: list[GapNote],
    queue: "deque[tuple[Node, int]]",
) -> None:
    """Append one Hop and either enqueue the neighbor for further
    expansion or, if it's an unresolved external sink, record a gap
    instead -- there's nothing further the graph knows past that node."""
    # The directed edge actually stored by add_edge is (parent, neighbor)
    # for a forward walk (we're following parent.out_edges), but
    # (neighbor, parent) for a reverse walk (we're following
    # parent.in_edges, so the real edge runs neighbor -> parent).
    if direction == "forward":
        edge_from, edge_to = parent.canonical_id, neighbor.canonical_id
    else:
        edge_from, edge_to = neighbor.canonical_id, parent.canonical_id

    hops.append(
        Hop(
            canonical_id=neighbor.canonical_id,
            file_path=neighbor.file_path,
            hop_index=new_depth,
            relation_type=relation_type,
            parent_canonical_id=parent.canonical_id,
            metadata=graph.get_edge_metadata(edge_from, edge_to, relation_type),
        )
    )
    if neighbor.canonical_id.startswith(_EXTERNAL_PREFIXES):
        gaps.append(
            GapNote(
                canonical_id=neighbor.canonical_id,
                reason=(
                    "unresolved external symbol/module -- "
                    "trace cannot continue past this node"
                ),
            )
        )
    else:
        queue.append((neighbor, new_depth))


def traced_path(
    graph: CodebaseGraph,
    start_cid: str,
    relation_types: set[str] | None,
    direction: str,
    max_depth: int,
    max_nodes: int,
) -> TraceResult:
    """Ordered, per-hop-evidenced BFS from `start_cid` -- unlike
    `bfs_traversal`, tracks the parent/relation_type that first reached
    each node, and stops computation (not just output) the instant
    `max_nodes` hops have been recorded.

    Caller must have already resolved `start_cid` to a real node
    (`resolve_start_symbol`); this raises `KeyError` if it hasn't.
    """
    start_node = graph.get_node(start_cid)
    if start_node is None:
        raise KeyError(f"start_cid not present in graph: {start_cid}")

    resolved_start = ResolvedStart(
        canonical_id=start_node.canonical_id, file_path=start_node.file_path
    )
    hops: list[Hop] = []
    gaps: list[GapNote] = []
    visited: set[str] = {start_node.canonical_id}
    queue: deque[tuple[Node, int]] = deque([(start_node, 0)])
    truncated = False

    while queue and not truncated:
        current_node, depth = queue.popleft()
        if depth >= max_depth:
            continue

        edges = (
            current_node.out_edges if direction == "forward" else current_node.in_edges
        )
        for relation_type, neighbors in edges.items():
            if relation_types and relation_type not in relation_types:
                continue
            for neighbor in sorted(neighbors, key=lambda n: n.canonical_id):
                if neighbor.canonical_id in visited:
                    continue
                if len(hops) >= max_nodes:
                    truncated = True
                    break
                visited.add(neighbor.canonical_id)
                _record_hop(
                    graph,
                    neighbor,
                    relation_type,
                    current_node,
                    depth + 1,
                    direction,
                    hops,
                    gaps,
                    queue,
                )
            if truncated:
                break

    return TraceResult(
        resolved_start=resolved_start,
        relation_types=sorted(relation_types) if relation_types else [],
        direction=direction,
        max_depth=max_depth,
        hops=hops,
        truncated=truncated,
        gaps=gaps,
    )


def _reconstruct_path(
    hops_by_cid: dict[str, Hop], start_cid: str, hop: Hop
) -> list[str]:
    path = [hop.canonical_id]
    current = hop
    while current.parent_canonical_id in hops_by_cid:
        current = hops_by_cid[current.parent_canonical_id]
        path.append(current.canonical_id)
    path.append(start_cid)
    path.reverse()
    return path


def assess_impact(
    graph: CodebaseGraph,
    start_cid: str,
    max_depth: int,
    max_candidates: int,
) -> ImpactResult:
    """Candidate-affected-set: reverse CALL/IMPORTS/INHERITS/OVERRIDES
    traversal from `start_cid`, merged into one candidate list where a
    node reached via more than one relation type carries every basis it
    was found under -- never just the first/strongest one. Explicitly a
    candidate set, not a claim of guaranteed breakage.

    Caller must have already resolved `start_cid`; raises `KeyError`
    otherwise (mirrors `traced_path`).
    """
    start_node = graph.get_node(start_cid)
    if start_node is None:
        raise KeyError(f"start_cid not present in graph: {start_cid}")

    resolved_start = ResolvedStart(
        canonical_id=start_node.canonical_id, file_path=start_node.file_path
    )
    candidates: dict[str, ImpactCandidate] = {}
    truncated = False

    for relation_type in IMPACT_RELATION_TYPES:
        remaining_budget = max_candidates - len(candidates)
        if remaining_budget <= 0:
            truncated = True
            break

        result = traced_path(
            graph,
            start_cid,
            relation_types={relation_type},
            direction="reverse",
            max_depth=max_depth,
            max_nodes=remaining_budget,
        )
        if result.truncated:
            truncated = True

        hops_by_cid = {hop.canonical_id: hop for hop in result.hops}
        for hop in result.hops:
            if hop.canonical_id not in candidates and len(candidates) >= max_candidates:
                truncated = True
                break
            basis = ImpactBasis(
                relation_type=relation_type,
                hop_distance=hop.hop_index,
                path=_reconstruct_path(hops_by_cid, start_node.canonical_id, hop),
                metadata=hop.metadata,
            )
            existing = candidates.get(hop.canonical_id)
            if existing is None:
                candidates[hop.canonical_id] = ImpactCandidate(
                    canonical_id=hop.canonical_id,
                    file_path=hop.file_path,
                    basis=[basis],
                )
            else:
                candidates[hop.canonical_id] = ImpactCandidate(
                    canonical_id=existing.canonical_id,
                    file_path=existing.file_path,
                    basis=[*existing.basis, basis],
                )

    return ImpactResult(
        resolved_start=resolved_start,
        relation_types_considered=list(IMPACT_RELATION_TYPES),
        max_depth=max_depth,
        candidates=list(candidates.values()),
        truncated=truncated,
    )
