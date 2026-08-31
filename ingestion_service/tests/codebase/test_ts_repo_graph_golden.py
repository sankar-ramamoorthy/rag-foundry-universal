# ingestion_service/tests/codebase/test_ts_repo_graph_golden.py
"""
WP-L2 golden-file + determinism tests over the checked-in fixture repo at
tests/fixtures/ts_repo/ (spec.md's "Fixture repo" Key Entity; SC-001,
SC-002, SC-003, SC-004, SC-005). The exact expected node/edge inventory
lives here (data-model.md deliberately doesn't duplicate it) — this is
the single source of truth for what "correct" means for this fixture.
"""
from pathlib import Path
from uuid import uuid4

import pytest

from src.core.codebase.repo_graph_builder import RepoGraphBuilder

pytestmark = pytest.mark.unit

FIXTURE_ROOT = Path(__file__).resolve().parent.parent / "fixtures" / "ts_repo"


def _build():
    builder = RepoGraphBuilder(FIXTURE_ROOT, ingestion_id=uuid4())
    return builder.build()


def _entity_inventory(graph):
    return sorted(
        (e["artifact_type"], e["canonical_id"]) for e in graph.all_entities()
    )


def _relationship_inventory(graph):
    return sorted(
        (r["relation_type"], r["from_canonical_id"], r["to_canonical_id"])
        for r in graph.relationships
    )


EXPECTED_ENTITIES = sorted([
    ("EXTERNAL_MODULE", "EXTERNAL_MODULE:react"),
    ("EXTERNAL_SYMBOL", "EXTERNAL_SYMBOL:console.log"),
    ("EXTERNAL_SYMBOL", "EXTERNAL_SYMBOL:setTimeout"),
    ("MODULE", "src/animal.ts"),
    ("CLASS", "src/animal.ts#Animal"),
    ("METHOD", "src/animal.ts#Animal.speak"),
    ("MODULE", "src/dog.ts"),
    ("CLASS", "src/dog.ts#Dog"),
    ("METHOD", "src/dog.ts#Dog.move"),
    ("IMPORT", "src/dog.ts#import:./animal.Animal"),
    ("IMPORT", "src/dog.ts#import:./movable.Movable"),
    ("MODULE", "src/external.ts"),
    ("IMPORT", "src/external.ts#import:react.default"),
    ("FUNCTION", "src/external.ts#render"),
    ("MODULE", "src/index.ts"),
    ("IMPORT", "src/index.ts#import:./sub.default"),
    ("IMPORT", "src/index.ts#import:./util.helper"),
    ("FUNCTION", "src/index.ts#run"),
    ("MODULE", "src/legacy.js"),
    ("FUNCTION", "src/legacy.js#arrowExport"),
    ("IMPORT", "src/legacy.js#import:./util.helper"),
    ("MODULE", "src/movable.ts"),
    ("INTERFACE", "src/movable.ts#Movable"),
    ("INTERFACE", "src/movable.ts#Named"),
    ("INTERFACE", "src/movable.ts#Titled"),
    ("MODULE", "src/sub/index.ts"),
    ("FUNCTION", "src/sub/index.ts#default"),
    ("MODULE", "src/util.ts"),
    ("FUNCTION", "src/util.ts#helper"),
])

EXPECTED_RELATIONSHIPS = sorted([
    ("CALL", "src/dog.ts#Dog.move", "src/animal.ts#Animal.speak"),
    ("CALL", "src/index.ts#run", "src/sub/index.ts#default"),
    ("CALL", "src/index.ts#run", "src/util.ts#helper"),
    ("CALL", "src/legacy.js#arrowExport", "EXTERNAL_SYMBOL:console.log"),
    ("CALL", "src/legacy.js#arrowExport", "EXTERNAL_SYMBOL:setTimeout"),
    ("CALL", "src/legacy.js#arrowExport", "src/util.ts#helper"),
    ("DEFINES", "src/animal.ts", "src/animal.ts#Animal"),
    ("DEFINES", "src/animal.ts#Animal", "src/animal.ts#Animal.speak"),
    ("DEFINES", "src/dog.ts", "src/dog.ts#Dog"),
    ("DEFINES", "src/dog.ts#Dog", "src/dog.ts#Dog.move"),
    ("DEFINES", "src/external.ts", "src/external.ts#render"),
    ("DEFINES", "src/index.ts", "src/index.ts#run"),
    ("DEFINES", "src/legacy.js", "src/legacy.js#arrowExport"),
    ("DEFINES", "src/movable.ts", "src/movable.ts#Movable"),
    ("DEFINES", "src/movable.ts", "src/movable.ts#Named"),
    ("DEFINES", "src/movable.ts", "src/movable.ts#Titled"),
    ("DEFINES", "src/sub/index.ts", "src/sub/index.ts#default"),
    ("DEFINES", "src/util.ts", "src/util.ts#helper"),
    ("IMPORTS", "src/dog.ts", "src/animal.ts"),
    ("IMPORTS", "src/dog.ts", "src/movable.ts"),
    ("IMPORTS", "src/external.ts", "EXTERNAL_MODULE:react"),
    ("IMPORTS", "src/index.ts", "src/sub/index.ts"),
    ("IMPORTS", "src/index.ts", "src/util.ts"),
    ("IMPORTS", "src/legacy.js", "src/util.ts"),
    ("INHERITS", "src/dog.ts#Dog", "src/animal.ts#Animal"),
    ("INHERITS", "src/dog.ts#Dog", "src/movable.ts#Movable"),
    ("INHERITS", "src/movable.ts#Named", "src/movable.ts#Titled"),
])


def test_golden_entity_inventory():
    """SC-001: the fixture repo produces exactly this node set, zero
    unhandled exceptions during build()."""
    graph = _build()
    assert _entity_inventory(graph) == EXPECTED_ENTITIES


def test_golden_relationship_inventory():
    """SC-001/SC-002/SC-003/SC-004: imports, calls (incl. `this`), and
    extends/implements all resolve to exactly this edge set."""
    graph = _build()
    assert _relationship_inventory(graph) == EXPECTED_RELATIONSHIPS


def test_relative_imports_resolve_in_repo():
    """SC-002: 100% of relative-specifier imports resolve to their
    correct in-repo target module."""
    graph = _build()
    rels = _relationship_inventory(graph)
    assert ("IMPORTS", "src/index.ts", "src/util.ts") in rels
    assert ("IMPORTS", "src/index.ts", "src/sub/index.ts") in rels
    assert ("IMPORTS", "src/dog.ts", "src/animal.ts") in rels


def test_bare_import_becomes_one_external_module_node():
    """SC-002: bare specifiers resolve to one external node per package."""
    graph = _build()
    externals = [
        e for e in graph.all_entities()
        if e["artifact_type"] == "EXTERNAL_MODULE"
    ]
    assert [e["canonical_id"] for e in externals] == ["EXTERNAL_MODULE:react"]


def test_this_qualified_call_resolves_within_class():
    """SC-003: `this.speak()` inside Dog.move resolves to Animal.speak
    (Dog doesn't define its own speak — resolved via the class hierarchy,
    ADR-032 step 1 extension)."""
    graph = _build()
    rels = _relationship_inventory(graph)
    assert ("CALL", "src/dog.ts#Dog.move", "src/animal.ts#Animal.speak") in rels


def test_extends_and_implements_produce_inherits_edges():
    """SC-004: Dog extends Animal and implements Movable both produce
    INHERITS edges; interface-extends-interface does too."""
    graph = _build()
    rels = _relationship_inventory(graph)
    assert ("INHERITS", "src/dog.ts#Dog", "src/animal.ts#Animal") in rels
    assert ("INHERITS", "src/dog.ts#Dog", "src/movable.ts#Movable") in rels
    assert ("INHERITS", "src/movable.ts#Named", "src/movable.ts#Titled") in rels


def test_rebuild_determinism():
    """SC-005 / ADR-036: re-running ingestion on the unchanged fixture
    twice produces byte-identical node/edge sets."""
    first = _build()
    second = _build()
    assert _entity_inventory(first) == _entity_inventory(second)
    assert _relationship_inventory(first) == _relationship_inventory(second)


def test_interface_is_documentable_like_a_class():
    """FR-008: INTERFACE participates in DEFINES the same way CLASS does."""
    graph = _build()
    rels = _relationship_inventory(graph)
    assert ("DEFINES", "src/movable.ts", "src/movable.ts#Movable") in rels
