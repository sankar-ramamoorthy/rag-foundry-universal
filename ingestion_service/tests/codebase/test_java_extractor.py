# ingestion_service/tests/codebase/test_java_extractor.py
"""
JavaExtractor unit tests (WP-L4, issue #132). Mirrors
test_rust_extractor.py's style: inline source snippets, no DB/Docker,
asserting directly on the IR (SymbolRecord/ImportRecord/CallSite) this
extractor emits — GraphAssembler resolution itself is covered separately
in test_java_repo_graph_golden.py.
"""
import pytest

from src.core.extractors.treesitter.java import JavaExtractor

pytestmark = pytest.mark.unit


def _extract(source: str, relative_path: str = "src/main/java/com/acme/Sample.java"):
    return JavaExtractor(relative_path).extract(source)


def _by_kind(result, kind):
    return [s for s in result.symbols if s.kind == kind]


# ---------------------------------------------------------------------
# Symbol extraction
# ---------------------------------------------------------------------


def test_class_interface_enum_record_extracted_as_own_kinds():
    result = _extract(
        """
        class Animal { }
        interface Movable { }
        enum Status { ACTIVE, INACTIVE }
        record Point(int x, int y) { }
        """
    )
    assert [s.name for s in _by_kind(result, "CLASS")] == ["Animal"]
    assert [s.name for s in _by_kind(result, "INTERFACE")] == ["Movable"]
    assert [s.name for s in _by_kind(result, "ENUM")] == ["Status"]
    assert [s.name for s in _by_kind(result, "RECORD")] == ["Point"]


def test_methods_get_dot_joined_symbol_path():
    result = _extract(
        """
        class Animal {
            public String speak() { return "hi"; }
            public String run() { return "go"; }
        }
        """
    )
    methods = _by_kind(result, "METHOD")
    assert sorted(m.symbol_path for m in methods) == ["Animal.run", "Animal.speak"]
    assert all(m.parent_symbol_path == "Animal" for m in methods)


def test_nested_class_dot_joins_through_two_levels():
    result = _extract(
        """
        class Animal {
            class Tag {
                void tagMethod() { }
            }
        }
        """
    )
    classes = _by_kind(result, "CLASS")
    assert sorted(c.symbol_path for c in classes) == ["Animal", "Animal.Tag"]
    methods = _by_kind(result, "METHOD")
    assert [m.symbol_path for m in methods] == ["Animal.Tag.tagMethod"]
    assert methods[0].parent_symbol_path == "Animal.Tag"


def test_constructor_gets_init_symbol_name():
    result = _extract(
        """
        class Animal {
            public Animal(String name) { }
        }
        """
    )
    methods = _by_kind(result, "METHOD")
    assert [m.symbol_path for m in methods] == ["Animal.<init>"]


def test_overloaded_methods_collapse_with_signatures():
    result = _extract(
        """
        class Animal {
            public void overload(int x) { }
            public void overload(String x) { }
            public void overload(int x, int y) { }
        }
        """
    )
    methods = _by_kind(result, "METHOD")
    assert [m.symbol_path for m in methods] == ["Animal.overload"]
    assert methods[0].metadata["overload_signatures"] == [
        "overload(String)", "overload(int)", "overload(int, int)",
    ]


def test_single_method_has_no_overload_signatures_metadata():
    result = _extract("class Animal { public void speak() { } }")
    methods = _by_kind(result, "METHOD")
    assert "overload_signatures" not in methods[0].metadata


def test_interface_method_declaration_extracted_without_body():
    result = _extract("interface Movable { void moveTo(int x, int y); }")
    methods = _by_kind(result, "METHOD")
    assert [m.symbol_path for m in methods] == ["Movable.moveTo"]


def test_locally_nested_class_not_extracted():
    """A local class defined inside a method body is an implementation
    detail, not part of the public API surface — v1 does not extract it
    (mirrors Rust's identical decision for locally-nested `fn`)."""
    result = _extract(
        """
        class Outer {
            void run() {
                class Local {
                    void innerMethod() { }
                }
            }
        }
        """
    )
    classes = _by_kind(result, "CLASS")
    assert [c.symbol_path for c in classes] == ["Outer"]
    methods = _by_kind(result, "METHOD")
    assert [m.symbol_path for m in methods] == ["Outer.run"]


def test_extends_and_implements_land_on_bases_metadata():
    result = _extract(
        "class Dog extends Animal implements Movable, Serializable { }"
    )
    classes = _by_kind(result, "CLASS")
    assert classes[0].metadata["bases"] == ["Animal", "Movable", "Serializable"]


def test_generic_interface_base_unwrapped_to_bare_name():
    result = _extract("class Animal implements Comparable<Animal> { }")
    classes = _by_kind(result, "CLASS")
    assert classes[0].metadata["bases"] == ["Comparable"]


def test_annotations_land_on_metadata():
    result = _extract(
        """
        class Animal {
            @Override
            @Deprecated
            public void speak() { }
        }
        """
    )
    methods = _by_kind(result, "METHOD")
    assert methods[0].metadata["annotations"] == ["Override", "Deprecated"]


def test_package_recorded_on_module_and_type_metadata():
    result = _extract(
        "package com.acme;\nclass Animal { }",
        relative_path="src/main/java/com/acme/Animal.java",
    )
    module = _by_kind(result, "MODULE")[0]
    assert module.metadata["package"] == "com.acme"
    animal = _by_kind(result, "CLASS")[0]
    assert animal.metadata["package"] == "com.acme"
    assert animal.metadata["fqcn"] == "com.acme.Animal"


# ---------------------------------------------------------------------
# Calls
# ---------------------------------------------------------------------


def test_this_receiver_call():
    result = _extract(
        """
        class Animal {
            public String speak() { return "hi"; }
            public String describe() { return this.speak(); }
        }
        """
    )
    calls = [c for c in result.calls if c.callee_name == "speak"]
    assert len(calls) == 1
    assert calls[0].receiver == "this"
    assert calls[0].caller_symbol_path == "Animal.describe"


def test_bare_call_has_no_receiver():
    result = _extract(
        """
        class Animal {
            public String speak() { return "hi"; }
            public String describe() { return speak(); }
        }
        """
    )
    calls = [c for c in result.calls if c.callee_name == "speak"]
    assert len(calls) == 1
    assert calls[0].receiver is None
    assert calls[0].caller_symbol_path == "Animal.describe"


def test_qualified_call_has_receiver():
    result = _extract(
        """
        class Caller {
            public void run() {
                Util.calc(1);
            }
        }
        """
    )
    calls = [c for c in result.calls if c.callee_name == "calc"]
    assert len(calls) == 1
    assert calls[0].receiver == "Util"


def test_object_creation_becomes_init_call():
    result = _extract(
        """
        class Caller {
            public void run() {
                Animal a = new Animal("Rex");
            }
        }
        """
    )
    calls = [c for c in result.calls if c.callee_name == "<init>"]
    assert len(calls) == 1
    assert calls[0].receiver == "Animal"
    assert calls[0].caller_symbol_path == "Caller.run"


# ---------------------------------------------------------------------
# Imports
# ---------------------------------------------------------------------


def test_single_class_import_is_from_style():
    result = _extract("import com.acme.util.Util;\nclass Sample { }")
    imports = [i for i in result.imports if i.imported_name == "Util"]
    assert len(imports) == 1
    assert imports[0].raw_module == "com.acme.util"


def test_wildcard_import_recorded_unresolved():
    result = _extract("import com.acme.other.*;\nclass Sample { }")
    imports = [i for i in result.imports if i.imported_name == "*"]
    assert len(imports) == 1
    assert imports[0].raw_module == "com.acme.other"


def test_static_import_not_extracted():
    result = _extract("import static com.acme.Consts.MAX;\nclass Sample { }")
    assert result.imports == []
