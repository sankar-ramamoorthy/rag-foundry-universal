# ingestion_service/tests/codebase/test_java_repo_graph_golden.py
"""
WP-L4 golden-file + determinism tests over the checked-in fixture repo at
tests/fixtures/java_repo/ (issue #132 acceptance criteria). The exact
expected node/edge inventory lives here (mirrors
test_ts_repo_graph_golden.py/test_rust_repo_graph_golden.py's pattern) —
this is the single source of truth for what "correct" means for this
fixture.

Fixture is a small Maven-layout repo (`src/main/java/...`) deliberately
built to exercise: a package + nested class (Animal.Tag), interface
implementation producing both INHERITS and OVERRIDES edges, an
overloaded method collapsed into one METHOD entity with
metadata.overload_signatures, a cross-file `import com.acme.util.Util;`
+ `Util.calc()` call, a wildcard import, `new Animal(...)` construction,
and — critically — a same-package reference with NO import statement
(`Caller.java` using `Animal` from the same `com.acme` package), which
exercises JavaModuleConvention.implicit_bindings.
"""
from pathlib import Path
from uuid import uuid4

import pytest

from src.core.codebase.repo_graph_builder import RepoGraphBuilder

pytestmark = pytest.mark.unit

FIXTURE_ROOT = Path(__file__).resolve().parent.parent / "fixtures" / "java_repo"

_UTIL = "src/main/java/com/acme/util/Util.java#Util"
_MOVABLE = "src/main/java/com/acme/Movable.java#Movable"
_ANIMAL = "src/main/java/com/acme/Animal.java#Animal"
_TAG = "src/main/java/com/acme/Animal.java#Animal.Tag"
_CALLER = "src/main/java/com/acme/Caller.java#Caller"


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
    ("CLASS", _ANIMAL),
    ("CLASS", _TAG),
    ("CLASS", _CALLER),
    ("CLASS", _UTIL),
    ("EXTERNAL_MODULE", "EXTERNAL_MODULE:com"),
    ("EXTERNAL_SYMBOL", "EXTERNAL_SYMBOL:a.speak"),
    ("IMPORT", "src/main/java/com/acme/Animal.java#import:com.acme.other.*"),
    ("IMPORT", "src/main/java/com/acme/Animal.java#import:com.acme.util.Util"),
    ("INTERFACE", _MOVABLE),
    ("METHOD", f"{_ANIMAL}.<init>"),
    ("METHOD", f"{_TAG}.tagMethod"),
    ("METHOD", f"{_ANIMAL}.describe"),
    ("METHOD", f"{_ANIMAL}.moveTo"),
    ("METHOD", f"{_ANIMAL}.overload"),
    ("METHOD", f"{_ANIMAL}.scaled"),
    ("METHOD", f"{_ANIMAL}.speak"),
    ("METHOD", f"{_CALLER}.run"),
    ("METHOD", f"{_MOVABLE}.moveTo"),
    ("METHOD", f"{_UTIL}.calc"),
    ("MODULE", "src/main/java/com/acme/Animal.java"),
    ("MODULE", "src/main/java/com/acme/Caller.java"),
    ("MODULE", "src/main/java/com/acme/Movable.java"),
    ("MODULE", "src/main/java/com/acme/util/Util.java"),
])

EXPECTED_RELATIONSHIPS = sorted([
    ("CALL", f"{_ANIMAL}.describe", f"{_ANIMAL}.speak"),
    ("CALL", f"{_ANIMAL}.moveTo", f"{_ANIMAL}.speak"),
    ("CALL", f"{_ANIMAL}.scaled", f"{_UTIL}.calc"),
    ("CALL", f"{_CALLER}.run", "EXTERNAL_SYMBOL:a.speak"),
    ("CALL", f"{_CALLER}.run", f"{_ANIMAL}.<init>"),
    ("DEFINES", "src/main/java/com/acme/Animal.java", _ANIMAL),
    ("DEFINES", _ANIMAL, f"{_ANIMAL}.<init>"),
    ("DEFINES", _ANIMAL, _TAG),
    ("DEFINES", _ANIMAL, f"{_ANIMAL}.describe"),
    ("DEFINES", _ANIMAL, f"{_ANIMAL}.moveTo"),
    ("DEFINES", _ANIMAL, f"{_ANIMAL}.overload"),
    ("DEFINES", _ANIMAL, f"{_ANIMAL}.scaled"),
    ("DEFINES", _ANIMAL, f"{_ANIMAL}.speak"),
    ("DEFINES", _TAG, f"{_TAG}.tagMethod"),
    ("DEFINES", "src/main/java/com/acme/Caller.java", _CALLER),
    ("DEFINES", _CALLER, f"{_CALLER}.run"),
    ("DEFINES", "src/main/java/com/acme/Movable.java", _MOVABLE),
    ("DEFINES", _MOVABLE, f"{_MOVABLE}.moveTo"),
    ("DEFINES", "src/main/java/com/acme/util/Util.java", _UTIL),
    ("DEFINES", _UTIL, f"{_UTIL}.calc"),
    ("IMPORTS", "src/main/java/com/acme/Animal.java", "EXTERNAL_MODULE:com"),
    (
        "IMPORTS", "src/main/java/com/acme/Animal.java",
        "src/main/java/com/acme/util/Util.java",
    ),
    ("INHERITS", _ANIMAL, _MOVABLE),
    ("OVERRIDES", f"{_ANIMAL}.moveTo", f"{_MOVABLE}.moveTo"),
])


def test_golden_entity_inventory():
    """The fixture repo produces exactly this node set, zero unhandled
    exceptions during build()."""
    graph = _build()
    assert _entity_inventory(graph) == EXPECTED_ENTITIES


def test_golden_relationship_inventory():
    """Package/nested-class extraction, interface implementation,
    overload collapsing, cross-file explicit imports, and same-package
    implicit references all resolve to exactly this edge set."""
    graph = _build()
    assert _relationship_inventory(graph) == EXPECTED_RELATIONSHIPS


def test_cross_file_import_resolves():
    """issue #132: `import com.acme.util.Util;` + `Util.calc()` resolves
    cross-file when `com/acme/util/Util.java` is in-repo."""
    graph = _build()
    rels = _relationship_inventory(graph)
    assert ("CALL", f"{_ANIMAL}.scaled", f"{_UTIL}.calc") in rels
    assert (
        "IMPORTS", "src/main/java/com/acme/Animal.java",
        "src/main/java/com/acme/util/Util.java",
    ) in rels


def test_same_package_reference_resolves_without_import():
    """`Caller.java` references `Animal` from the same `com.acme`
    package with no `import` statement — JavaModuleConvention.
    implicit_bindings must supply this binding."""
    graph = _build()
    rels = _relationship_inventory(graph)
    assert ("CALL", f"{_CALLER}.run", f"{_ANIMAL}.<init>") in rels


def test_overloaded_methods_collapse_to_one_entity_with_signatures():
    """Design decision: two `overload(...)` methods with different
    parameter types collapse into one METHOD entity (no canonical-id
    collision), with metadata.overload_signatures listing each."""
    graph = _build()
    entity = graph.get_entity(f"{_ANIMAL}.overload")
    assert entity is not None
    assert entity["metadata"]["overload_signatures"] == [
        "overload(String)", "overload(int)",
    ]


def test_nested_class_gets_dot_joined_symbol_path():
    """`Outer.Inner.method` nesting (ADR-031) — Animal.Tag.tagMethod."""
    graph = _build()
    ids = [e["canonical_id"] for e in graph.all_entities()]
    assert _TAG in ids
    assert f"{_TAG}.tagMethod" in ids


def test_interface_implementation_produces_inherits_and_overrides():
    """`implements Movable` produces INHERITS; overriding `moveTo`
    produces OVERRIDES via the existing generic hierarchy walk."""
    graph = _build()
    rels = _relationship_inventory(graph)
    assert ("INHERITS", _ANIMAL, _MOVABLE) in rels
    assert ("OVERRIDES", f"{_ANIMAL}.moveTo", f"{_MOVABLE}.moveTo") in rels


def test_interface_method_declaration_is_extracted():
    """Unlike WP-L2's TS interface-member skip, Java interface method
    declarations (no body) ARE extracted as METHOD symbols."""
    graph = _build()
    ids = [e["canonical_id"] for e in graph.all_entities()]
    assert f"{_MOVABLE}.moveTo" in ids


def test_rebuild_determinism():
    """ADR-036: re-running ingestion on the unchanged fixture twice
    produces byte-identical node/edge sets."""
    first = _build()
    second = _build()
    assert _entity_inventory(first) == _entity_inventory(second)
    assert _relationship_inventory(first) == _relationship_inventory(second)


def test_package_recorded_in_metadata_not_identity():
    """Package declaration lands in metadata.package/fqcn — identity
    stays purely path-derived."""
    graph = _build()
    entity = graph.get_entity(_ANIMAL)
    assert entity["metadata"]["package"] == "com.acme"
    assert entity["metadata"]["fqcn"] == "com.acme.Animal"
