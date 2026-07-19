# rag_orchestrator/tests/test_traversal_selector_routing.py
"""
Issue #30 Part 2: traversal routing must match whole words/phrases.

The old selector used substring matching with a bare "in" term, so any
query containing ingest/print/main/find routed to traverse_defines and
caller queries never reached traverse_incoming_calls.
"""
import pytest

from src.retrieval.traversal_selector import select_traversal_strategies
from src.retrieval.codebase_queries import (
    traverse_calls,
    traverse_defines,
    traverse_incoming_calls,
    traverse_incoming_imports,
)

pytestmark = pytest.mark.unit


def selected_funcs(query):
    return [s.func for s in select_traversal_strategies(query, {"a.py#f"})]


CASES = [
    # caller intent — the Part 2 regression cases
    ("what functions call ingest_repo?", [traverse_incoming_calls]),
    ("who calls main?", [traverse_incoming_calls]),
    ("callers of add", [traverse_incoming_calls]),
    ("what calls build_pipeline", [traverse_incoming_calls]),
    ("which methods call save?", [traverse_incoming_calls]),
    ("functions called by run", [traverse_incoming_calls]),
    # structure intent still works
    ("methods in math_utils.py", [traverse_defines]),
    ("what functions are defined in service.py", [traverse_defines]),
    ("classes in the ingestion module", [traverse_defines]),
    ("methods of RepoGraphBuilder", [traverse_defines]),
    # callee intent
    ("what does main call?", [traverse_calls]),
    ("show the function calls made by run_rag", [traverse_calls]),
    # import intent
    ("what imports repo_naming", [traverse_incoming_imports]),
    ("modules imported by service.py", [traverse_incoming_imports]),
    # substring words no longer hijack routing → default (defines+calls)
    ("explain ingest_repo", [traverse_defines, traverse_calls]),
    ("how does print_summary work", [traverse_defines, traverse_calls]),
    ("describe the main entrypoint", [traverse_defines, traverse_calls]),
    ("find the string formatting logic", [traverse_defines, traverse_calls]),
]


@pytest.mark.parametrize("query,expected", CASES, ids=[c[0] for c in CASES])
def test_query_routes_to_expected_strategies(query, expected):
    assert selected_funcs(query) == expected
