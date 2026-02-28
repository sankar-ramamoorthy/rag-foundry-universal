# rag_orchestrator/src/retrieval/traversal_selector.py
"""
Keyword-driven traversal strategy selection.
"""
from typing import List, Callable, Set
from functools import partial
import logging

from .codebase_queries import (
    traverse_defines, 
    traverse_calls, 
    traverse_incoming_calls, 
    traverse_incoming_imports,
    CodebaseGraph,
    Node
)

logger = logging.getLogger(__name__)

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
    
    # PRIORITY 1: "methods/functions/classes in X"
    if any(term in query_lower for term in ["method", "methods", "function", "functions", "class", "classes", "in"]):
        logger.debug("Selected: traverse_defines (methods/functions in X)")
        strategies.append(partial(traverse_defines, depth=1))
    
    # PRIORITY 2: "what calls X", "callers of X", "called by X"
    elif any(term in query_lower for term in ["callers", "calls", "called by", "who calls"]):
        logger.debug("Selected: traverse_incoming_calls (callers)")
        strategies.append(partial(traverse_incoming_calls, depth=1))
    
    # PRIORITY 3: "what does X call"
    elif any(term in query_lower for term in ["calls", "call"]):
        logger.debug("Selected: traverse_calls (outgoing calls)")
        strategies.append(partial(traverse_calls, depth=1))
    
    # PRIORITY 4: "imports X"
    elif "import" in query_lower:
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
