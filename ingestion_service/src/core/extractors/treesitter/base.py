# ingestion_service/src/core/extractors/treesitter/base.py
"""
Shared tree-sitter plumbing for WP-L2+ extractors (DOCS/audit/
03-Multi-Language-Graph-Plan.md §3): a per-grammar Parser/Language cache
(tree-sitter grammars are process-wide singletons — one Language/Parser
instance is reused across every file of that language, never rebuilt per
file) and a thin `.scm` query-runner so per-language extractor code stays
declarative-query-driven rather than hand-walking cursors, per the plan
doc's WP-L2 directions.

API verified directly against the installed tree_sitter 0.25.2 in this
repo's venv (research.md): `Language(lang_fn())`, `Parser(language)`,
`Query(language, source)`, `QueryCursor(query).captures(node)`.
"""
from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from typing import Dict, List

from tree_sitter import Language, Node, Parser, Query, QueryCursor
import tree_sitter_javascript as ts_javascript
import tree_sitter_typescript as ts_typescript

_TSX_SUFFIXES = (".tsx",)
_TS_SUFFIXES = (".ts",)
_JS_SUFFIXES = (".js", ".jsx", ".mjs", ".cjs")


@lru_cache(maxsize=None)
def _language_for(suffix: str) -> Language:
    if suffix in _TSX_SUFFIXES:
        return Language(ts_typescript.language_tsx())
    if suffix in _TS_SUFFIXES:
        return Language(ts_typescript.language_typescript())
    if suffix in _JS_SUFFIXES:
        return Language(ts_javascript.language())
    raise ValueError(f"No tree-sitter grammar registered for suffix {suffix!r}")


@lru_cache(maxsize=None)
def _parser_for(suffix: str) -> Parser:
    return Parser(_language_for(suffix))


def parser_for_path(relative_path: str) -> Parser:
    """The cached Parser for a file's language, selected by suffix."""
    suffix = Path(relative_path).suffix
    return _parser_for(suffix)


def language_for_path(relative_path: str) -> Language:
    suffix = Path(relative_path).suffix
    return _language_for(suffix)


@lru_cache(maxsize=None)
def _compiled_query(language: Language, query_source: str) -> Query:
    return Query(language, query_source)


def run_query(
    language: Language, query_source: str, root: Node
) -> Dict[str, List[Node]]:
    """Run one `.scm` query against a subtree, returning capture name ->
    matched nodes. Queries are compiled once per (language, source) pair
    and cached — WP-L2's Directions call for declarative queries per
    concept rather than hand-walked cursors; the actual field-level
    inspection of each matched node still happens in the extractor, since
    tree-sitter query syntax alone can't express "only a named-binding
    arrow function, not an anonymous one" cleanly."""
    query = _compiled_query(language, query_source)
    cursor = QueryCursor(query)
    return cursor.captures(root)
