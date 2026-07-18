# ingestion_service/tests/codebase/test_graph_build_linear.py
"""
F-07: O(N) graph construction.

Acceptance criteria:
- artifact text extraction is byte-identical to the old per-artifact
  ast.get_source_segment path (ADR-030 rebuild determinism);
- each file is parsed a bounded number of times, not once per artifact;
- two builds of the same repo produce identical entities/relationships.
"""
import ast
import pytest
from uuid import uuid4

from src.core.codebase.repo_graph_builder import (
    RepoGraphBuilder,
    _source_segment,
    _splitlines_no_ff,
)

pytestmark = pytest.mark.unit


TRICKY_SOURCES = [
    # method indentation + nested class + unicode
    (
        "class Service:\n"
        '    """docstring with unicode: café"""\n'
        "\n"
        "    def run(self):\n"
        "        return 1\n"
        "\n"
        "    class Inner:\n"
        "        def ping(self):\n"
        "            return 0\n"
    ),
    # decorated function (segment starts at def, not the decorator)
    (
        "import functools\n"
        "\n"
        "@functools.lru_cache(maxsize=None)\n"
        "def cached(n):\n"
        "    return n * 2\n"
    ),
    # single-line def
    "def oneliner(): return 42\n",
    # form feed between functions — must NOT be treated as a line break
    "def first():\n    return 1\n\f\ndef second():\n    return first()\n",
    # CR and CRLF line endings
    "def win():\r\n    return 42\r\n",
    "def mac():\r    return 7\r",
    # no trailing newline
    "def tailless():\n    return 3",
]


@pytest.mark.parametrize("source", TRICKY_SOURCES)
def test_source_segment_matches_ast_get_source_segment(source):
    """_source_segment over pre-split lines must be byte-identical to
    ast.get_source_segment for every def/class node."""
    tree = ast.parse(source)
    lines = _splitlines_no_ff(source)
    checked = 0
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef,
                             ast.ClassDef)):
            expected = ast.get_source_segment(source, node)
            assert _source_segment(lines, node) == expected
            checked += 1
    assert checked > 0


@pytest.mark.parametrize("source", TRICKY_SOURCES)
def test_splitlines_no_ff_reassembles_source(source):
    """Splitting must be lossless — segments are sliced from these lines."""
    assert "".join(_splitlines_no_ff(source)) == source


def _make_repo(root, n_files=3, n_funcs=10):
    for i in range(n_files):
        parts = []
        for j in range(n_funcs):
            parts.append(f"def f_{i}_{j}():\n    return {j}\n\n")
        parts.append(
            f"class K{i}:\n    def m(self):\n        return f_{i}_0()\n"
        )
        (root / f"mod{i}.py").write_text("".join(parts), encoding="utf-8")


def test_each_file_parsed_bounded_times(tmp_path, monkeypatch):
    """A file with N artifacts must not be parsed N times (F-07). The
    extractor parses once and the text indexer parses once — allow 2."""
    _make_repo(tmp_path, n_files=2, n_funcs=15)

    parse_calls = []
    real_parse = ast.parse

    def counting_parse(source, *args, **kwargs):
        parse_calls.append(1)
        return real_parse(source, *args, **kwargs)

    monkeypatch.setattr(ast, "parse", counting_parse)

    graph = RepoGraphBuilder(tmp_path, ingestion_id=str(uuid4())).build()

    n_py_files = 2
    artifacts = len(graph.entities)
    assert artifacts > n_py_files * 10, "fixture produced too few artifacts"
    assert len(parse_calls) <= 2 * n_py_files, (
        f"{len(parse_calls)} ast.parse calls for {n_py_files} files — "
        "per-artifact re-parsing is back"
    )


def test_rebuild_is_deterministic(tmp_path):
    """ADR-030: same repo + same ingestion_id → identical graph."""
    _make_repo(tmp_path)
    g1 = RepoGraphBuilder(tmp_path, ingestion_id="fixed-id").build()
    g2 = RepoGraphBuilder(tmp_path, ingestion_id="fixed-id").build()

    assert list(g1.entities.keys()) == list(g2.entities.keys())
    assert {c: e["text"] for c, e in g1.entities.items()} == \
           {c: e["text"] for c, e in g2.entities.items()}
    assert g1.relationships == g2.relationships


def test_entities_by_id_index_matches_entities(tmp_path):
    """The F-07 id index must resolve to the same objects a full scan
    over entities would find."""
    _make_repo(tmp_path)
    graph = RepoGraphBuilder(tmp_path, ingestion_id=str(uuid4())).build()

    for entity in graph.all_entities():
        entity_id = entity.get("id")
        if entity_id is None:
            continue
        indexed = graph.get_entity_by_id(entity_id)
        assert indexed is not None
        # same canonical resolution as a linear scan (last write wins in
        # both dicts, so the objects must be identical)
        assert indexed is graph.entities[indexed["canonical_id"]]

    assert graph.get_entity_by_id("no/such/id") is None


def test_method_text_extraction_end_to_end(tmp_path):
    """Spot-check real extracted text: indented method block, exact."""
    (tmp_path / "svc.py").write_text(
        "class Service:\n"
        "    def run(self):\n"
        "        return 1\n",
        encoding="utf-8",
    )
    graph = RepoGraphBuilder(tmp_path, ingestion_id=str(uuid4())).build()

    method = graph.entities.get("svc.py#Service.run")
    assert method is not None
    assert method["text"] == "def run(self):\n        return 1"

    klass = graph.entities.get("svc.py#Service")
    assert klass is not None
    assert klass["text"].startswith("class Service:")
