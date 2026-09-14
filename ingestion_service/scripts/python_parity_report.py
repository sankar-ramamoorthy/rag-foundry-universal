#!/usr/bin/env python
"""
WP-L5 manual A/B parity report (DOCS/audit/03-Multi-Language-Graph-Plan.md
WP-L5 section, issue #134): run PythonASTExtractor and
PythonTreeSitterExtractor over the SAME real, external repo (a clone
outside this repo — too large/noisy to check in) and report the diff.

The committed CI parity gate is test_python_parity_harness.py, run
against the small checked-in tests/fixtures/python_repo_valid/ fixture.
This script exists to run the SAME comparison against real-world repos —
the ">=5 varied real repos" acceptance criterion — before flipping
PYTHON_TREESITTER_ENABLED's Stage B default in config.py. Record each
run's repo/commit + diff status in DOCS/audit/03-Multi-Language-Graph-Plan.md.

Usage:
    uv run python scripts/python_parity_report.py <path-to-repo>

Exit code 0 iff both the structural and semantic diffs are empty.
"""
from __future__ import annotations

import os
import sys
from pathlib import Path
from uuid import uuid4

sys.stdout.reconfigure(encoding="utf-8", errors="backslashreplace")

os.environ.setdefault("DATABASE_URL", "postgresql://parity:parity@localhost/parity")

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.core.codebase.repo_graph_builder import RepoGraphBuilder  # noqa: E402
from src.core.config import reset_settings_cache  # noqa: E402

_METADATA_KEYS_COMPARED = ("args", "is_async", "bases", "doc_type")


def _build(repo_root: Path, *, treesitter: bool):
    os.environ["PYTHON_TREESITTER_ENABLED"] = "true" if treesitter else "false"
    os.environ["PYTHON_TREESITTER_AUTO_FALLBACK"] = "false"
    reset_settings_cache()
    return RepoGraphBuilder(repo_root, ingestion_id=uuid4()).build()


def _entity_ids(graph):
    return {(e["artifact_type"], e["canonical_id"]) for e in graph.all_entities()}


def _relationship_ids(graph):
    return {
        (r["relation_type"], r["from_canonical_id"], r["to_canonical_id"])
        for r in graph.relationships
    }


def _entity_semantics(graph):
    semantics = {}
    for e in graph.all_entities():
        key = (e["artifact_type"], e["canonical_id"])
        metadata = e.get("metadata") or {}
        semantics[key] = (
            e.get("name"),
            e.get("symbol_path"),
            e.get("parent_symbol_path"),
            e.get("text"),
            tuple(sorted(
                (k, tuple(v) if isinstance(v, list) else v)
                for k, v in metadata.items()
                if k in _METADATA_KEYS_COMPARED
            )),
        )
    return semantics


def main(repo_arg: str) -> int:
    repo_root = Path(repo_arg).resolve()
    if not repo_root.is_dir():
        print(f"not a directory: {repo_root}", file=sys.stderr)
        return 2

    ast_graph = _build(repo_root, treesitter=False)
    ts_graph = _build(repo_root, treesitter=True)

    entity_diff = _entity_ids(ast_graph) ^ _entity_ids(ts_graph)
    rel_diff = _relationship_ids(ast_graph) ^ _relationship_ids(ts_graph)

    ast_sem = _entity_semantics(ast_graph)
    ts_sem = _entity_semantics(ts_graph)
    semantic_diff = {
        key: (ast_sem.get(key), ts_sem.get(key))
        for key in set(ast_sem) | set(ts_sem)
        if ast_sem.get(key) != ts_sem.get(key)
    }

    print(f"repo: {repo_root}")
    print(f"entity structural diff ({len(entity_diff)}):")
    for item in sorted(entity_diff):
        print(f"  {item}")
    print(f"relationship structural diff ({len(rel_diff)}):")
    for item in sorted(rel_diff):
        print(f"  {item}")
    print(f"semantic IR diff ({len(semantic_diff)}):")
    for key, (ast_val, ts_val) in semantic_diff.items():
        print(f"  {key}: ast={ast_val!r} tree-sitter={ts_val!r}")

    ok = not entity_diff and not rel_diff and not semantic_diff
    print("RESULT:", "PARITY (zero diff)" if ok else "DIFF FOUND")
    return 0 if ok else 1


if __name__ == "__main__":
    if len(sys.argv) != 2:
        print(f"usage: {sys.argv[0]} <path-to-repo>", file=sys.stderr)
        sys.exit(2)
    sys.exit(main(sys.argv[1]))
