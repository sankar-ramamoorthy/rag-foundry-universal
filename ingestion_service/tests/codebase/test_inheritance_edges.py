# ingestion_service/tests/codebase/test_inheritance_edges.py
"""
WP-G5: CLASS --INHERITS--> CLASS and METHOD --OVERRIDES--> METHOD edges,
plus self.x() falling back to base-class methods.
"""
import pytest
from uuid import uuid4

from src.core.codebase.repo_graph_builder import RepoGraphBuilder

pytestmark = pytest.mark.unit


def _write_repo(tmp_path):
    (tmp_path / "base.py").write_text(
        "class Animal:\n"
        "    def speak(self):\n"
        "        return 'generic'\n"
        "    def eat(self):\n"
        "        return 'eating'\n",
        encoding="utf-8",
    )
    (tmp_path / "dog.py").write_text(
        "from base import Animal\n"
        "\n"
        "class Dog(Animal):\n"
        "    def speak(self):\n"
        "        return 'woof'\n"
        "    def fetch(self):\n"
        "        return self.eat()\n",  # eat() defined only on the base
        encoding="utf-8",
    )
    (tmp_path / "models.py").write_text(
        "from pydantic import BaseModel\n"
        "\n"
        "class Config(BaseModel):\n"
        "    pass\n",
        encoding="utf-8",
    )
    (tmp_path / "same_file.py").write_text(
        "class Base:\n"
        "    def run(self):\n"
        "        return 0\n"
        "\n"
        "class Child(Base):\n"
        "    def run(self):\n"
        "        return 1\n",
        encoding="utf-8",
    )


@pytest.fixture()
def graph(tmp_path):
    _write_repo(tmp_path)
    return RepoGraphBuilder(tmp_path, ingestion_id=str(uuid4())).build()


def _edges(graph, relation_type):
    return {
        (r["from_canonical_id"], r["to_canonical_id"])
        for r in graph.relationships
        if r["relation_type"] == relation_type
    }


def test_cross_file_inherits_edge_via_import(graph):
    """class Dog(Animal) with Animal imported → INHERITS edge."""
    assert ("dog.py#Dog", "base.py#Animal") in _edges(graph, "INHERITS")


def test_same_file_inherits_edge(graph):
    assert ("same_file.py#Child", "same_file.py#Base") in _edges(
        graph, "INHERITS"
    )


def test_override_yields_overrides_edge(graph):
    """Dog.speak overriding Animal.speak → OVERRIDES edge."""
    assert ("dog.py#Dog.speak", "base.py#Animal.speak") in _edges(
        graph, "OVERRIDES"
    )
    assert ("same_file.py#Child.run", "same_file.py#Base.run") in _edges(
        graph, "OVERRIDES"
    )


def test_non_overriding_method_has_no_overrides_edge(graph):
    overrides = _edges(graph, "OVERRIDES")
    assert not any(f == "dog.py#Dog.fetch" for f, _ in overrides)


def test_self_call_resolves_via_inheritance(graph):
    """self.eat() inside Dog.fetch resolves to Animal.eat (defined only
    on the base class)."""
    call_edges = _edges(graph, "CALL")
    assert ("dog.py#Dog.fetch", "base.py#Animal.eat") in call_edges


def test_external_base_links_to_external_symbol(graph):
    """class Config(BaseModel) with pydantic external → EXTERNAL_SYMBOL."""
    inherits = _edges(graph, "INHERITS")
    targets = {to for frm, to in inherits if frm == "models.py#Config"}
    assert targets == {"EXTERNAL_SYMBOL:pydantic.BaseModel"}


def test_inherits_metadata_carries_base_string_and_confidence(graph):
    edge = next(
        r for r in graph.relationships
        if r["relation_type"] == "INHERITS"
        and r["from_canonical_id"] == "dog.py#Dog"
    )
    assert edge["relationship_metadata"]["bases"] == ["Animal"]
    assert edge["relationship_metadata"]["confidence"] == 1.0


def test_rebuild_determinism(tmp_path):
    _write_repo(tmp_path)
    ingestion_id = str(uuid4())

    def snapshot():
        g = RepoGraphBuilder(tmp_path, ingestion_id=ingestion_id).build()
        return [
            (r["from_canonical_id"], r["to_canonical_id"], r["relation_type"])
            for r in g.relationships
            if r["relation_type"] in {"INHERITS", "OVERRIDES", "CALL"}
        ]

    assert snapshot() == snapshot()


def test_subscripted_generic_base_resolves_to_class(tmp_path):
    """class Stack(Container[int]) resolves the base to Container."""
    (tmp_path / "gen.py").write_text(
        "class Container:\n"
        "    pass\n"
        "\n"
        "class Stack(Container[int]):\n"
        "    pass\n",
        encoding="utf-8",
    )
    graph = RepoGraphBuilder(tmp_path, ingestion_id=str(uuid4())).build()
    assert ("gen.py#Stack", "gen.py#Container") in _edges(graph, "INHERITS")


def test_inheritance_cycle_does_not_hang(tmp_path):
    """Mutually-inheriting classes (illegal at runtime, parseable) must
    not loop the hierarchy walk."""
    (tmp_path / "cycle.py").write_text(
        "class A(B):\n"
        "    def go(self):\n"
        "        return self.missing()\n"
        "\n"
        "class B(A):\n"
        "    pass\n",
        encoding="utf-8",
    )
    graph = RepoGraphBuilder(tmp_path, ingestion_id=str(uuid4())).build()
    inherits = _edges(graph, "INHERITS")
    assert ("cycle.py#A", "cycle.py#B") in inherits
    assert ("cycle.py#B", "cycle.py#A") in inherits
