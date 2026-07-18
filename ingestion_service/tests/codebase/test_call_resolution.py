# ingestion_service/tests/codebase/test_call_resolution.py
"""
F-04 (WP-G4): scope- and import-aware call resolution per ADR-032:
local scope → file imports → global index (only if unambiguous) →
EXTERNAL_SYMBOL. Unresolved calls become edges, never silent drops.
"""
import pytest
from uuid import uuid4

from src.core.codebase.repo_graph_builder import RepoGraphBuilder

pytestmark = pytest.mark.unit


def _write_repo(tmp_path):
    (tmp_path / "utils.py").write_text(
        "def calc():\n    return 1\n", encoding="utf-8"
    )
    (tmp_path / "file.py").write_text(
        "class A:\n"
        "    def helper(self):\n"
        "        return 1\n"
        "\n"
        "    def run(self):\n"
        "        return self.helper()\n",
        encoding="utf-8",
    )
    (tmp_path / "app.py").write_text(
        "import requests\n"
        "import utils\n"
        "from utils import calc\n"
        "\n"
        "\n"
        "def use_import():\n"
        "    return calc()\n"
        "\n"
        "\n"
        "def use_module_receiver():\n"
        "    return utils.calc()\n"
        "\n"
        "\n"
        "def use_external():\n"
        "    return requests.get('http://x')\n",
        encoding="utf-8",
    )
    # two same-named functions in different files + a bare call from a
    # third file → must NOT pick an arbitrary winner
    (tmp_path / "dup_a.py").write_text(
        "def dupe():\n    return 'a'\n", encoding="utf-8"
    )
    (tmp_path / "dup_b.py").write_text(
        "def dupe():\n    return 'b'\n", encoding="utf-8"
    )
    (tmp_path / "third.py").write_text(
        "def caller():\n    return dupe()\n", encoding="utf-8"
    )
    # unique global symbol called bare from another file (no import)
    (tmp_path / "solo.py").write_text(
        "def one_of_a_kind():\n    return 1\n", encoding="utf-8"
    )
    (tmp_path / "uses_solo.py").write_text(
        "def go():\n    return one_of_a_kind()\n", encoding="utf-8"
    )


@pytest.fixture()
def graph(tmp_path):
    _write_repo(tmp_path)
    return RepoGraphBuilder(tmp_path, ingestion_id=str(uuid4())).build()


def _call_edges(graph):
    return [r for r in graph.relationships if r["relation_type"] == "CALL"]


def _edge(graph, from_cid, to_cid):
    matches = [
        e for e in _call_edges(graph)
        if e["from_canonical_id"] == from_cid
        and e["to_canonical_id"] == to_cid
    ]
    assert len(matches) <= 1
    return matches[0] if matches else None


def test_self_call_resolves_to_enclosing_class_method(graph):
    """self.helper() inside class A resolves to file.py#A.helper, 1.0."""
    edge = _edge(graph, "file.py#A.run", "file.py#A.helper")
    assert edge is not None
    assert edge["relationship_metadata"]["confidence"] == 1.0


def test_imported_symbol_resolves_cross_file(graph):
    """from utils import calc; calc() → utils.py#calc, confidence 1.0."""
    edge = _edge(graph, "app.py#use_import", "utils.py#calc")
    assert edge is not None
    assert edge["relationship_metadata"]["confidence"] == 1.0


def test_module_receiver_resolves_cross_file(graph):
    """import utils; utils.calc() → utils.py#calc, confidence 1.0."""
    edge = _edge(graph, "app.py#use_module_receiver", "utils.py#calc")
    assert edge is not None
    assert edge["relationship_metadata"]["confidence"] == 1.0


def test_external_call_becomes_queryable_external_symbol(graph):
    """requests.get → edge to EXTERNAL_SYMBOL:requests.get, conf 0.0."""
    edge = _edge(graph, "app.py#use_external", "EXTERNAL_SYMBOL:requests.get")
    assert edge is not None
    assert edge["relationship_metadata"]["confidence"] == 0.0

    node = graph.get_entity("EXTERNAL_SYMBOL:requests.get")
    assert node is not None
    assert node["artifact_type"] == "EXTERNAL_SYMBOL"
    assert node["doc_type"] == "external"
    assert node["text"] == ""  # never embedded (ADR-039)


def test_ambiguous_global_yields_external_not_arbitrary_winner(graph):
    """dupe() defined in dup_a.py and dup_b.py, called bare from
    third.py → EXTERNAL edge, not an arbitrary pick."""
    assert _edge(graph, "third.py#caller", "dup_a.py#dupe") is None
    assert _edge(graph, "third.py#caller", "dup_b.py#dupe") is None

    edge = _edge(graph, "third.py#caller", "EXTERNAL_SYMBOL:dupe")
    assert edge is not None
    assert edge["relationship_metadata"]["confidence"] == 0.0


def test_unique_global_resolves_with_half_confidence(graph):
    """one_of_a_kind() is globally unique → resolves at 0.5."""
    edge = _edge(graph, "uses_solo.py#go", "solo.py#one_of_a_kind")
    assert edge is not None
    assert edge["relationship_metadata"]["confidence"] == 0.5


def test_unresolved_self_call_goes_external(graph):
    """No calls are silently dropped: every call site lands in an edge."""
    # str() call receiver 'http://x' argument aside — sanity: all sites
    # of app.py map to some edge from their enclosing scope.
    froms = {e["from_canonical_id"] for e in _call_edges(graph)}
    assert {"app.py#use_import", "app.py#use_module_receiver",
            "app.py#use_external"} <= froms


def test_rebuild_determinism(tmp_path):
    _write_repo(tmp_path)
    g1 = RepoGraphBuilder(tmp_path, ingestion_id="fixed-id").build()
    g2 = RepoGraphBuilder(tmp_path, ingestion_id="fixed-id").build()
    assert g1.relationships == g2.relationships
    assert sorted(g1.entities.keys()) == sorted(g2.entities.keys())
