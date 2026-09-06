# rag_orchestrator/src/retrieval/traversal_selector.py
"""
Keyword-driven traversal strategy selection.
"""
from typing import Dict, List, Callable, Set
from functools import partial
import logging
import re

from .codebase_queries import (
    traverse_defines,
    traverse_calls,
    traverse_incoming_calls,
    traverse_incoming_imports,
    traverse_superclasses,
    traverse_subclasses,
    traverse_overrides,
    traverse_overridden_by,
    CodebaseGraph,
    Node
)

logger = logging.getLogger(__name__)

# Issue #30 Part 2: intent matching uses whole-word/phrase regexes, most
# specific first. The old substring `if "in" in query` hijacked nearly
# every query (ingest, print, main, find, …) into traverse_defines, so
# caller queries never reached traverse_incoming_calls.
#
# WP-G6: the if/elif chain is now an ordered rule table — data, not
# code — so adding a strategy is one row. First matching row wins;
# matching stays deterministic (no LLM router, per ADR-045).

def _s(traversal) -> Callable[[CodebaseGraph, str], List[Node]]:
    return partial(traversal, depth=1)


# (intent, patterns, strategy factories) — evaluated top to bottom.
_RULE_TABLE: List[tuple] = [
    (
        "callers",
        [
            r"\bwho\s+calls\b",
            r"\bwhat\s+calls\b",
            r"\bcallers?\s+of\b",
            r"\bcalled\s+by\b",
            r"\bcallers\b",
            r"\bwhat\s+(?:functions?|methods?|classes?)\s+calls?\b",
            r"\bwhich\s+(?:functions?|methods?|classes?)\s+calls?\b",
        ],
        [lambda: _s(traverse_incoming_calls)],
    ),
    (
        # WP-G6: "what subclasses Calculator", "which classes extend X"
        "subclasses",
        [
            r"\bsubclass(?:es|ed)?\b",
            r"\bextends\b",
            r"\b(?:what|which|classes?)\s+extend\b",
            r"\bwhat\s+inherits\s+from\b",
            r"\bderived\s+(?:classes?\s+)?(?:of|from)\b",
            r"\bchild(?:ren)?\s+class(?:es)?\b",
        ],
        [lambda: _s(traverse_subclasses)],
    ),
    (
        # WP-G6: "base class of X", "what does X inherit from"
        "superclasses",
        [
            r"\bsuperclass(?:es)?\b",
            r"\bbase\s+class(?:es)?\b",
            r"\bparent\s+class(?:es)?\b",
            r"\binherits?\s+from\b",
        ],
        [lambda: _s(traverse_superclasses)],
    ),
    (
        # WP-G6: overrides run both directions — "what overrides X" and
        # "what does X override" share vocabulary too often to split.
        "overrides",
        [r"\boverrid(?:e|es|den|ing)\b"],
        [lambda: _s(traverse_overrides), lambda: _s(traverse_overridden_by)],
    ),
    (
        "structure",
        [
            r"\b(?:methods?|functions?|classes?)\s+(?:defined\s+)?in\b",
            r"\b(?:methods?|functions?|classes?)\s+of\b",
            r"\bdefined\s+in\b",
        ],
        [lambda: _s(traverse_defines)],
    ),
    (
        "callees",
        [
            r"\bwhat\s+does\s+\S+\s+call\b",
            r"\bcalls?\b",
        ],
        [lambda: _s(traverse_calls)],
    ),
    (
        "imports",
        [
            r"\bimported\s+by\b",
            r"\bimports?\b",
        ],
        [lambda: _s(traverse_incoming_imports)],
    ),
]

_DEFAULT_STRATEGIES = [
    lambda: _s(traverse_defines),
    lambda: _s(traverse_calls),
]


def _matches_any(query_lower: str, patterns: List[str]) -> bool:
    return any(re.search(p, query_lower) for p in patterns)


def select_traversal_strategies(
    query: str,
    seed_canonical_ids: Set[str]
) -> List[Callable[[CodebaseGraph, str], List[Node]]]:
    """
    Select traversal strategies based on query intent via the ordered
    rule table; first matching row wins, else default (defines + calls).

    >>> strategies = select_traversal_strategies("methods in math_utils.py", ...)
    >>> len(strategies) > 0
    True
    """
    query_lower = query.lower()

    for intent, patterns, factories in _RULE_TABLE:
        if _matches_any(query_lower, patterns):
            logger.debug(f"Selected intent: {intent}")
            strategies = [factory() for factory in factories]
            break
    else:
        logger.debug("Selected: default (defines + calls)")
        strategies = [factory() for factory in _DEFAULT_STRATEGIES]

    logger.info(
        f"Selected {len(strategies)} traversal strategies for query: '{query[:50]}...'"
    )
    return strategies

def _seed_and_defines_descendants(graph: CodebaseGraph, start_cid: str) -> List[str]:
    """INHERITS/OVERRIDES/CALL edges live on CLASS/METHOD nodes, never on
    the enclosing MODULE. Vector search often seeds the coarser MODULE
    (or CLASS, for a method-level edge) artifact instead of the exact
    symbol, which otherwise makes those traversal strategies silently
    return nothing even though the edge exists one DEFINES hop away.
    Expand the anchor set to the seed plus everything it (transitively)
    defines, so class/method-scoped strategies still find it."""
    if graph is None:
        return [start_cid]
    descendants = traverse_defines(graph, start_cid, depth=2)
    return [start_cid] + [n.canonical_id for n in descendants]


def execute_traversals(
    graph: CodebaseGraph,
    start_canonical_id: str,
    strategies: List[Callable[[CodebaseGraph, str], List[Node]]]
) -> List[tuple[Node, int]]:
    """
    Execute all selected traversal strategies from the seed and its
    DEFINES descendants (see `_seed_and_defines_descendants`).

    Returns (node, strategy_index) pairs rather than bare nodes: the index
    is the position within `strategies` that discovered the node (its
    lowest index, if more than one strategy found it). Issue #89: callers
    use this to prefer nodes found by an earlier-listed, more structurally
    authoritative strategy (e.g. DEFINES before CALL — see
    `_DEFAULT_STRATEGIES`) once nodes are deduplicated, instead of that
    signal being computed here and then thrown away.
    """
    all_expanded: List[tuple[Node, int]] = []
    anchors = _seed_and_defines_descendants(graph, start_canonical_id)

    for strategy_index, strategy in enumerate(strategies):
        for anchor in anchors:
            try:
                nodes = strategy(graph, anchor)
                all_expanded.extend((node, strategy_index) for node in nodes)
                logger.debug(f"Strategy returned {len(nodes)} nodes from {anchor}")
            except Exception as e:
                logger.warning(f"Traversal strategy failed: {e}")
                continue

    # Deduplicate by canonical_id, keeping the lowest (most authoritative)
    # strategy_index seen for each node. A DEFINES descendant used purely
    # as an extra anchor (e.g. Dog.speak when the seed was Dog) can
    # legitimately also be the answer itself for a "structure" query, so
    # anchors are not excluded here — only the true seed is, by the caller.
    best_index: Dict[str, int] = {}
    node_by_cid: Dict[str, Node] = {}
    for node, strategy_index in all_expanded:
        cid = node.canonical_id
        node_by_cid.setdefault(cid, node)
        if cid not in best_index or strategy_index < best_index[cid]:
            best_index[cid] = strategy_index

    logger.info(f"Total unique expanded nodes: {len(node_by_cid)}")
    return [(node_by_cid[cid], best_index[cid]) for cid in node_by_cid]

def execute_traversals_from_seeds(
    graph: CodebaseGraph,
    seed_canonical_ids: Set[str],
    strategies: List[Callable[[CodebaseGraph, str], List[Node]]]
) -> List[Node]:
    """
    F-12: expand from ALL seed canonical_ids, not one arbitrary seed.

    Previously only the longest seed string was traversed and every other
    vector-search hit was silently dropped from graph expansion. Seeds are
    bounded by vector-search top_k, so this stays cheap. Iteration is
    sorted for deterministic results; nodes are deduplicated across seeds.
    """
    # Issue #30 Part 3: rank expanded nodes so downstream caps keep the
    # most seed-adjacent ones. All strategies currently traverse at
    # depth=1, so "reached from more seeds" is the adjacency signal;
    # canonical_id breaks ties deterministically.
    #
    # Issue #89: strategy_index (see execute_traversals) is now the primary
    # key, ahead of seed-hit count. A node reached only via CALL/IMPORT from
    # one seed used to rank ahead of, or tie alphabetically against, a true
    # DEFINES child of that same seed -- e.g. an external library symbol
    # crowding out the seed module's own helper functions for the
    # MAX_EXPANDED_DOCS cap purely on canonical_id ordering. Confirmed
    # failure case: DOCS/test_results/
    # 2026-09-03-rag-retrieval-quality-linux-tailscale-baseline.md section 13.
    seed_hits: Dict[str, int] = {}
    best_strategy_index: Dict[str, int] = {}
    node_by_cid: Dict[str, Node] = {}
    for start_cid in sorted(seed_canonical_ids):
        for node, strategy_index in execute_traversals(graph, start_cid, strategies):
            cid = node.canonical_id
            seed_hits[cid] = seed_hits.get(cid, 0) + 1
            node_by_cid.setdefault(cid, node)
            prev_index = best_strategy_index.get(cid)
            if prev_index is None or strategy_index < prev_index:
                best_strategy_index[cid] = strategy_index

    ranked = sorted(
        node_by_cid.values(),
        key=lambda n: (
            best_strategy_index[n.canonical_id],
            -seed_hits[n.canonical_id],
            n.canonical_id,
        ),
    )
    logger.info(
        f"Multi-seed expansion: {len(seed_canonical_ids)} seeds → "
        f"{len(ranked)} unique nodes"
    )
    return ranked
