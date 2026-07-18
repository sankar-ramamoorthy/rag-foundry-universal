# ingestion_service/tests/codebase/test_imports_edges.py
"""
F-02 (WP-G2): MODULE --IMPORTS--> MODULE edges materialize from IMPORT
artifacts; external imports get one EXTERNAL_MODULE node per root package.
"""
import pytest
from uuid import uuid4

from src.core.codebase.repo_graph_builder import RepoGraphBuilder

pytestmark = pytest.mark.unit


def _write_repo(tmp_path):
    (tmp_path / "pkg").mkdir()
    (tmp_path / "pkg" / "__init__.py").write_text("", encoding="utf-8")
    (tmp_path / "pkg" / "util.py").write_text(
        "def helper():\n    return 1\n", encoding="utf-8"
    )
    (tmp_path / "pkg" / "sibling.py").write_text(
        "from . import util\n"
        "from .util import helper\n",
        encoding="utf-8",
    )
    (tmp_path / "app.py").write_text(
        "from pkg.util import helper\n"
        "import numpy\n"
        "import numpy.linalg\n",
        encoding="utf-8",
    )
    (tmp_path / "other.py").write_text(
        "import numpy as np\n"
        "import pkg.util\n",
        encoding="utf-8",
    )


@pytest.fixture()
def graph(tmp_path):
    _write_repo(tmp_path)
    return RepoGraphBuilder(tmp_path, ingestion_id=str(uuid4())).build()


def _imports_edges(graph):
    return [
        r for r in graph.relationships if r["relation_type"] == "IMPORTS"
    ]


def _edge_set(graph):
    return {
        (e["from_canonical_id"], e["to_canonical_id"])
        for e in _imports_edges(graph)
    }


def test_from_import_yields_module_edge(graph):
    """`from pkg.util import helper` in app.py → app.py IMPORTS pkg/util.py"""
    assert ("app.py", "pkg/util.py") in _edge_set(graph)


def test_relative_imports_resolve(graph):
    """`from . import util` and `from .util import helper` in pkg/sibling.py"""
    assert ("pkg/sibling.py", "pkg/util.py") in _edge_set(graph)


def test_plain_dotted_import_resolves(graph):
    """`import pkg.util` in other.py → other.py IMPORTS pkg/util.py"""
    assert ("other.py", "pkg/util.py") in _edge_set(graph)


def test_external_module_node_is_singleton(graph):
    """`import numpy`, `import numpy.linalg`, `import numpy as np` across
    two files → exactly one EXTERNAL_MODULE node named numpy."""
    externals = [
        e for e in graph.all_entities()
        if e["artifact_type"] == "EXTERNAL_MODULE"
    ]
    assert len(externals) == 1
    node = externals[0]
    assert node["name"] == "numpy"
    assert node["canonical_id"] == "EXTERNAL_MODULE:numpy"
    assert node["doc_type"] == "external"
    assert node["text"] == ""  # never embedded (ADR-039)

    assert ("app.py", "EXTERNAL_MODULE:numpy") in _edge_set(graph)
    assert ("other.py", "EXTERNAL_MODULE:numpy") in _edge_set(graph)


def test_edges_aggregate_per_module_pair(graph):
    """app.py imports numpy twice (numpy, numpy.linalg) → one edge,
    both imported names in metadata."""
    edges = [
        e for e in _imports_edges(graph)
        if e["from_canonical_id"] == "app.py"
        and e["to_canonical_id"] == "EXTERNAL_MODULE:numpy"
    ]
    assert len(edges) == 1
    meta = edges[0]["relationship_metadata"]
    assert meta["count"] == 2
    assert [p[0] for p in meta["imports"]] == ["numpy", "numpy.linalg"]


def test_import_bindings_recorded_for_call_resolution(graph):
    """F-04 consumes per-file bindings (ADR-032 layer 2)."""
    app = graph.import_bindings["app.py"]
    assert app["helper"] == {
        "kind": "symbol", "module_cid": "pkg/util.py", "symbol": "helper",
    }
    other = graph.import_bindings["other.py"]
    assert other["np"] == {"kind": "external_module", "dotted": "numpy"}
    assert other["pkg.util"] == {"kind": "module", "module_cid": "pkg/util.py"}


def test_rebuild_determinism_with_imports(tmp_path):
    _write_repo(tmp_path)
    g1 = RepoGraphBuilder(tmp_path, ingestion_id="fixed-id").build()
    g2 = RepoGraphBuilder(tmp_path, ingestion_id="fixed-id").build()
    assert g1.relationships == g2.relationships
    assert sorted(g1.entities.keys()) == sorted(g2.entities.keys())
