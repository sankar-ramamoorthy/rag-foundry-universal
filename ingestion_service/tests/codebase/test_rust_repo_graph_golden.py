# ingestion_service/tests/codebase/test_rust_repo_graph_golden.py
"""
WP-L3 golden-file + determinism tests over the checked-in fixture repo at
tests/fixtures/rust_repo/ (issue #130 acceptance criteria). The exact
expected node/edge inventory lives here (mirrors
test_ts_repo_graph_golden.py's pattern) — this is the single source of
truth for what "correct" means for this fixture.

Fixture is a two-crate workspace (crate_a, crate_b) deliberately built to
exercise: methods merged across three separate impl blocks for one struct
(two inherent `impl Animal` blocks plus `impl Movable for Animal`),
`impl Trait for Type` resolving to an INHERITS edge via
_resolve_inherit_records (not same-file metadata.bases), `use crate::…`
and `use super::…` resolution (including the `foo/mod.rs` convention),
`Type::method()`/`Self::method()`/`self.method()` call shapes, and two
same-named structs (`Item`) in different crates producing zero canonical-
id collisions.
"""
from pathlib import Path
from uuid import uuid4

import pytest

from src.core.codebase.repo_graph_builder import RepoGraphBuilder

pytestmark = pytest.mark.unit

FIXTURE_ROOT = Path(__file__).resolve().parent.parent / "fixtures" / "rust_repo"


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
    ("EXTERNAL_SYMBOL", "EXTERNAL_SYMBOL:self.sku.clone"),
    ("EXTERNAL_SYMBOL", "EXTERNAL_SYMBOL:to_string"),
    ("IMPORT", "crate_a/src/kennel.rs#import:.Animal"),
    ("IMPORT", "crate_a/src/shapes/square.rs#import:.Circle"),
    ("METHOD", "crate_a/src/kennel.rs#Dog.bark"),
    ("METHOD", "crate_a/src/kennel.rs#Dog.greet"),
    ("METHOD", "crate_a/src/kennel.rs#Dog.make_animal"),
    ("METHOD", "crate_a/src/kennel.rs#Dog.make_default"),
    ("METHOD", "crate_a/src/kennel.rs#Dog.new"),
    ("METHOD", "crate_a/src/lib.rs#Animal.describe"),
    ("METHOD", "crate_a/src/lib.rs#Animal.move_to"),
    ("METHOD", "crate_a/src/lib.rs#Animal.new"),
    ("METHOD", "crate_a/src/lib.rs#Animal.speak"),
    ("METHOD", "crate_a/src/shapes/mod.rs#Circle.area"),
    ("METHOD", "crate_a/src/shapes/mod.rs#Circle.new"),
    ("METHOD", "crate_a/src/shapes/mod.rs#Circle.radius_squared"),
    ("METHOD", "crate_a/src/shapes/square.rs#Square.area"),
    ("METHOD", "crate_a/src/shapes/square.rs#Square.make_circle"),
    ("METHOD", "crate_a/src/shapes/square.rs#Square.new"),
    ("METHOD", "crate_b/src/lib.rs#Item.label"),
    ("METHOD", "crate_b/src/lib.rs#Item.new"),
    ("MODULE", "crate_a/src/kennel.rs"),
    ("MODULE", "crate_a/src/lib.rs"),
    ("MODULE", "crate_a/src/shapes/mod.rs"),
    ("MODULE", "crate_a/src/shapes/square.rs"),
    ("MODULE", "crate_b/src/lib.rs"),
    ("STRUCT", "crate_a/src/kennel.rs#Dog"),
    ("STRUCT", "crate_a/src/lib.rs#Animal"),
    ("STRUCT", "crate_a/src/lib.rs#Item"),
    ("STRUCT", "crate_a/src/shapes/mod.rs#Circle"),
    ("STRUCT", "crate_a/src/shapes/square.rs#Square"),
    ("STRUCT", "crate_b/src/lib.rs#Item"),
    ("TRAIT", "crate_a/src/lib.rs#Movable"),
])

_DOG = "crate_a/src/kennel.rs#Dog"
_ANIMAL = "crate_a/src/lib.rs#Animal"
_MOVABLE = "crate_a/src/lib.rs#Movable"
_CIRCLE = "crate_a/src/shapes/mod.rs#Circle"
_SQUARE = "crate_a/src/shapes/square.rs#Square"
_ITEM_B = "crate_b/src/lib.rs#Item"

EXPECTED_RELATIONSHIPS = sorted([
    ("CALL", f"{_DOG}.greet", f"{_DOG}.bark"),
    ("CALL", f"{_DOG}.make_animal", "EXTERNAL_SYMBOL:to_string"),
    ("CALL", f"{_DOG}.make_animal", f"{_ANIMAL}.new"),
    ("CALL", f"{_DOG}.make_default", f"{_DOG}.new"),
    ("CALL", f"{_DOG}.new", "EXTERNAL_SYMBOL:to_string"),
    ("CALL", f"{_ANIMAL}.describe", f"{_ANIMAL}.speak"),
    ("CALL", f"{_ANIMAL}.move_to", f"{_ANIMAL}.speak"),
    ("CALL", f"{_CIRCLE}.area", f"{_CIRCLE}.radius_squared"),
    ("CALL", f"{_SQUARE}.make_circle", f"{_CIRCLE}.new"),
    ("CALL", f"{_ITEM_B}.label", "EXTERNAL_SYMBOL:self.sku.clone"),
    ("DEFINES", "crate_a/src/kennel.rs", _DOG),
    ("DEFINES", _DOG, f"{_DOG}.bark"),
    ("DEFINES", _DOG, f"{_DOG}.greet"),
    ("DEFINES", _DOG, f"{_DOG}.make_animal"),
    ("DEFINES", _DOG, f"{_DOG}.make_default"),
    ("DEFINES", _DOG, f"{_DOG}.new"),
    ("DEFINES", "crate_a/src/lib.rs", _ANIMAL),
    ("DEFINES", "crate_a/src/lib.rs", "crate_a/src/lib.rs#Item"),
    ("DEFINES", "crate_a/src/lib.rs", _MOVABLE),
    ("DEFINES", _ANIMAL, f"{_ANIMAL}.describe"),
    ("DEFINES", _ANIMAL, f"{_ANIMAL}.move_to"),
    ("DEFINES", _ANIMAL, f"{_ANIMAL}.new"),
    ("DEFINES", _ANIMAL, f"{_ANIMAL}.speak"),
    ("DEFINES", "crate_a/src/shapes/mod.rs", _CIRCLE),
    ("DEFINES", _CIRCLE, f"{_CIRCLE}.area"),
    ("DEFINES", _CIRCLE, f"{_CIRCLE}.new"),
    ("DEFINES", _CIRCLE, f"{_CIRCLE}.radius_squared"),
    ("DEFINES", "crate_a/src/shapes/square.rs", _SQUARE),
    ("DEFINES", _SQUARE, f"{_SQUARE}.area"),
    ("DEFINES", _SQUARE, f"{_SQUARE}.make_circle"),
    ("DEFINES", _SQUARE, f"{_SQUARE}.new"),
    ("DEFINES", "crate_b/src/lib.rs", _ITEM_B),
    ("DEFINES", _ITEM_B, f"{_ITEM_B}.label"),
    ("DEFINES", _ITEM_B, f"{_ITEM_B}.new"),
    ("IMPORTS", "crate_a/src/kennel.rs", "crate_a/src/lib.rs"),
    ("IMPORTS", "crate_a/src/shapes/square.rs", "crate_a/src/shapes/mod.rs"),
    ("INHERITS", _ANIMAL, _MOVABLE),
])


def test_golden_entity_inventory():
    """The fixture repo produces exactly this node set, zero unhandled
    exceptions during build() — including two same-named `Item` structs
    in different crates producing distinct canonical ids (no collision,
    issue #130 acceptance criterion)."""
    graph = _build()
    assert _entity_inventory(graph) == EXPECTED_ENTITIES


def test_golden_relationship_inventory():
    """`use crate::…`/`use super::…` imports, self/Self::/Type:: calls,
    and `impl Trait for Type` all resolve to exactly this edge set."""
    graph = _build()
    assert _relationship_inventory(graph) == EXPECTED_RELATIONSHIPS


def test_no_canonical_id_collision_across_crates():
    """issue #130: a workspace with two crates produces no canonical-ID
    collisions between same-named modules/types (crate_a::Item vs
    crate_b::Item)."""
    graph = _build()
    ids = [e["canonical_id"] for e in graph.all_entities()]
    assert len(ids) == len(set(ids))
    assert "crate_a/src/lib.rs#Item" in ids
    assert "crate_b/src/lib.rs#Item" in ids


def test_type_qualified_and_self_receiver_calls_resolve():
    """issue #130: `Type::new()` and self-receiver method calls resolve
    to the expected target entity."""
    graph = _build()
    rels = _relationship_inventory(graph)
    # Type::method()
    assert ("CALL", f"{_DOG}.make_animal", f"{_ANIMAL}.new") in rels
    # Self::method() (rewritten to the enclosing impl's own type)
    assert ("CALL", f"{_DOG}.make_default", f"{_DOG}.new") in rels
    # self.method()
    assert ("CALL", f"{_DOG}.greet", f"{_DOG}.bark") in rels


def test_methods_merge_across_impl_blocks():
    """WP-L3 design decision #1: methods from THREE separate impl blocks
    for `Animal` (two inherent `impl Animal` blocks plus
    `impl Movable for Animal`) all attach to the same STRUCT entity."""
    graph = _build()
    rels = _relationship_inventory(graph)
    animal_methods = {
        to_cid for (rel, from_cid, to_cid) in rels
        if rel == "DEFINES" and from_cid == _ANIMAL
    }
    assert animal_methods == {
        f"{_ANIMAL}.new",
        f"{_ANIMAL}.speak",
        f"{_ANIMAL}.describe",
        f"{_ANIMAL}.move_to",
    }


def test_impl_trait_for_type_produces_inherits_edge():
    """WP-L3 design decision #2: `impl Trait for Type` resolves to an
    INHERITS edge via _resolve_inherit_records, independent of same-file
    metadata.bases."""
    graph = _build()
    rels = _relationship_inventory(graph)
    assert ("INHERITS", _ANIMAL, _MOVABLE) in rels


def test_use_crate_and_use_super_resolve_in_repo():
    """`use crate::Animal;` (crate-root-relative) and `use super::Circle;`
    (one level up, into a `mod.rs`) both resolve to their correct
    in-repo target module."""
    graph = _build()
    rels = _relationship_inventory(graph)
    assert ("IMPORTS", "crate_a/src/kennel.rs", "crate_a/src/lib.rs") in rels
    assert (
        "IMPORTS", "crate_a/src/shapes/square.rs", "crate_a/src/shapes/mod.rs"
    ) in rels


def test_macro_invocations_recorded_as_metadata_not_calls():
    """issue #130: macro bodies are never inspected as call evidence —
    only a per-owner invocation count is recorded in metadata."""
    graph = _build()
    speak = graph.get_entity("crate_a/src/lib.rs#Animal.speak")
    assert speak["metadata"]["macro_invocations"] == 1
    rels = _relationship_inventory(graph)
    assert not any(
        to_cid.startswith("EXTERNAL_SYMBOL:format") for (_, _, to_cid) in rels
    )


def test_rebuild_determinism():
    """ADR-036: re-running ingestion on the unchanged fixture twice
    produces byte-identical node/edge sets."""
    first = _build()
    second = _build()
    assert _entity_inventory(first) == _entity_inventory(second)
    assert _relationship_inventory(first) == _relationship_inventory(second)


def test_struct_and_trait_are_documentable():
    """STRUCT/ENUM/TRAIT participate in DEFINES the same way CLASS does
    (DOCUMENTABLE_TYPES, WP-L3 additive touch)."""
    graph = _build()
    rels = _relationship_inventory(graph)
    assert ("DEFINES", "crate_a/src/lib.rs", "crate_a/src/lib.rs#Movable") in rels
    assert ("DEFINES", "crate_a/src/lib.rs", "crate_a/src/lib.rs#Animal") in rels
