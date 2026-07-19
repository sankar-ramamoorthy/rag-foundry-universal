# rag_orchestrator/src/retrieval/traversal_selector.py
"""
Keyword-driven traversal strategy selection.
"""
from typing import List, Callable, Set
from functools import partial
import logging
import re

from .codebase_queries import (
    traverse_defines,
    traverse_calls,
    traverse_incoming_calls,
    traverse_incoming_imports,
    CodebaseGraph,
    Node
)

logger = logging.getLogger(__name__)

# Issue #30 Part 2: intent matching uses whole-word/phrase regexes, most
# specific first. The old substring `if "in" in query` hijacked nearly
# every query (ingest, print, main, find, …) into traverse_defines, so
# caller queries never reached traverse_incoming_calls.

_CALLER_PATTERNS = [
    r"\bwho\s+calls\b",
    r"\bwhat\s+calls\b",
    r"\bcallers?\s+of\b",
    r"\bcalled\s+by\b",
    r"\bcallers\b",
    r"\bwhat\s+(?:functions?|methods?|classes?)\s+calls?\b",
    r"\bwhich\s+(?:functions?|methods?|classes?)\s+calls?\b",
]

_STRUCTURE_PATTERNS = [
    r"\b(?:methods?|functions?|classes?)\s+(?:defined\s+)?in\b",
    r"\b(?:methods?|functions?|classes?)\s+of\b",
    r"\bdefined\s+in\b",
]

_CALLEE_PATTERNS = [
    r"\bwhat\s+does\s+\S+\s+call\b",
    r"\bcalls?\b",
]

_IMPORT_PATTERNS = [
    r"\bimported\s+by\b",
    r"\bimports?\b",
]


def _matches_any(query_lower: str, patterns: List[str]) -> bool:
    return any(re.search(p, query_lower) for p in patterns)


def select_traversal_strategies(
    query: str,
    seed_canonical_ids: Set[str]
) -> List[Callable[[CodebaseGraph, str], List[Node]]]:
    """
    Select traversal strategies based on query intent.

    >>> strategies = select_traversal_strategies("methods in math_utils.py", ...)
    >>> len(strategies) > 0
    True
    """
    query_lower = query.lower()
    strategies = []

    # PRIORITY 1: caller intent — "who calls X", "callers of X",
    # "what functions call X"
    if _matches_any(query_lower, _CALLER_PATTERNS):
        logger.debug("Selected: traverse_incoming_calls (callers)")
        strategies.append(partial(traverse_incoming_calls, depth=1))

    # PRIORITY 2: structure intent — "methods in X", "defined in X"
    elif _matches_any(query_lower, _STRUCTURE_PATTERNS):
        logger.debug("Selected: traverse_defines (methods/functions in X)")
        strategies.append(partial(traverse_defines, depth=1))

    # PRIORITY 3: callee intent — "what does X call", "X calls Y"
    elif _matches_any(query_lower, _CALLEE_PATTERNS):
        logger.debug("Selected: traverse_calls (outgoing calls)")
        strategies.append(partial(traverse_calls, depth=1))

    # PRIORITY 4: import intent — "imports X", "imported by X"
    elif _matches_any(query_lower, _IMPORT_PATTERNS):
        logger.debug("Selected: traverse_incoming_imports (imports)")
        strategies.append(partial(traverse_incoming_imports, depth=1))

    # DEFAULT: Comprehensive exploration
    else:
        logger.debug("Selected: default (defines + calls)")
        strategies.extend([
            partial(traverse_defines, depth=1),
            partial(traverse_calls, depth=1)
        ])

    logger.info(f"Selected {len(strategies)} traversal strategies for query: '{query[:50]}...'")
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
            logger.debug(f"Strategy returned {len(nodes)} nodes from {start_canonical_id}")
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
    all_nodes: List[Node] = []
    for start_cid in sorted(seed_canonical_ids):
        all_nodes.extend(execute_traversals(graph, start_cid, strategies))

    unique_nodes = {node.canonical_id: node for node in all_nodes}.values()
    logger.info(
        f"Multi-seed expansion: {len(seed_canonical_ids)} seeds → "
        f"{len(unique_nodes)} unique nodes"
    )
    return list(unique_nodes)
