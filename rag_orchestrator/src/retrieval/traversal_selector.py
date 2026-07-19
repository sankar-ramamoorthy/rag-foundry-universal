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

def execute_traversals(
    graph: CodebaseGraph,
    start_canonical_id: str,
    strategies: List[Callable[[CodebaseGraph, str], List[Node]]]
) -> List[Node]:
    """
    Execute all selected traversal strategies.
    """
    all_expanded_nodes = []

    for strategy in strategies:
        try:
            nodes = strategy(graph, start_canonical_id)
            all_expanded_nodes.extend(nodes)
            logger.debug(
                f"Strategy returned {len(nodes)} nodes from {start_canonical_id}"
            )
        except Exception as e:
            logger.warning(f"Traversal strategy failed: {e}")
            continue

    # Deduplicate by canonical_id
    unique_nodes = {node.canonical_id: node for node in all_expanded_nodes}.values()
    logger.info(f"Total unique expanded nodes: {len(unique_nodes)}")
    return list(unique_nodes)

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
    seed_hits: Dict[str, int] = {}
    node_by_cid: Dict[str, Node] = {}
    for start_cid in sorted(seed_canonical_ids):
        for node in execute_traversals(graph, start_cid, strategies):
            seed_hits[node.canonical_id] = seed_hits.get(node.canonical_id, 0) + 1
            node_by_cid.setdefault(node.canonical_id, node)

    ranked = sorted(
        node_by_cid.values(),
        key=lambda n: (-seed_hits[n.canonical_id], n.canonical_id),
    )
    logger.info(
        f"Multi-seed expansion: {len(seed_canonical_ids)} seeds → "
        f"{len(ranked)} unique nodes"
    )
    return ranked
