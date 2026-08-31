# ingestion_service/tests/codebase/test_graph_assembler_language.py
"""
WP-L6a (specs/003-language-aware-retrieval): every code symbol/import node
carries a dedicated `language` value, derived centrally in GraphAssembler
from the file suffix rather than per-extractor metadata (plan.md's
Constitution Exceptions table). Non-code nodes (markdown, external
placeholders) carry none.
"""
from pathlib import Path
from uuid import uuid4

import pytest

from src.core.codebase.graph_assembler import LANGUAGE_BY_SUFFIX, _language_for_path
from src.core.codebase.repo_graph_builder import RepoGraphBuilder

pytestmark = pytest.mark.unit

TS_FIXTURE_ROOT = Path(__file__).resolve().parent.parent / "fixtures" / "ts_repo"


def test_language_by_suffix_covers_python_and_ts_js():
    assert LANGUAGE_BY_SUFFIX[".py"] == "python"
    assert LANGUAGE_BY_SUFFIX[".ts"] == "typescript"
    assert LANGUAGE_BY_SUFFIX[".tsx"] == "typescript"
    for suffix in (".js", ".jsx", ".mjs", ".cjs"):
        assert LANGUAGE_BY_SUFFIX[suffix] == "javascript"


def test_language_for_path_recognized_suffix():
    assert _language_for_path("src/app.py") == "python"
    assert _language_for_path("src/widget.tsx") == "typescript"
    assert _language_for_path("src/legacy.js") == "javascript"


def test_language_for_path_unrecognized_suffix_is_none():
    assert _language_for_path("README.md") is None
    assert _language_for_path("data.json") is None


def test_language_for_path_empty_string_is_none():
    """EXTERNAL_MODULE/EXTERNAL_SYMBOL synthetic nodes use relative_path=""."""
    assert _language_for_path("") is None


def test_python_entities_carry_python_language(tmp_path):
    (tmp_path / "app.py").write_text("def run():\n    return 1\n", encoding="utf-8")
    graph = RepoGraphBuilder(tmp_path, ingestion_id=str(uuid4())).build()

    module = graph.get_entity("app.py")
    func = graph.get_entity("app.py#run")
    assert module["language"] == "python"
    assert func["language"] == "python"


def test_ts_repo_entities_carry_ts_or_js_language():
    graph = RepoGraphBuilder(TS_FIXTURE_ROOT, ingestion_id=str(uuid4())).build()

    ts_class = graph.get_entity("src/animal.ts#Animal")
    js_func = graph.get_entity("src/legacy.js#arrowExport")
    assert ts_class["language"] == "typescript"
    assert js_func["language"] == "javascript"


def test_external_and_markdown_like_nodes_carry_no_language():
    graph = RepoGraphBuilder(TS_FIXTURE_ROOT, ingestion_id=str(uuid4())).build()

    externals = [
        e for e in graph.all_entities()
        if e["artifact_type"] in ("EXTERNAL_MODULE", "EXTERNAL_SYMBOL")
    ]
    assert externals, "fixture must produce at least one external node"
    assert all(e.get("language") is None for e in externals)


def test_mixed_language_repo_each_file_gets_its_own_language(tmp_path):
    (tmp_path / "main.py").write_text("def run():\n    return 1\n", encoding="utf-8")
    (tmp_path / "util.ts").write_text(
        "export function helper() {\n  return 1;\n}\n", encoding="utf-8"
    )
    graph = RepoGraphBuilder(tmp_path, ingestion_id=str(uuid4())).build()

    assert graph.get_entity("main.py")["language"] == "python"
    assert graph.get_entity("util.ts")["language"] == "typescript"
