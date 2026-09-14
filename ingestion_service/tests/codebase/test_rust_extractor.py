# ingestion_service/tests/codebase/test_rust_extractor.py
"""
RustExtractor unit tests (WP-L3, issue #130). Mirrors
test_typescript_extractor.py's style: inline source snippets, no
DB/Docker, asserting directly on the IR (SymbolRecord/ImportRecord/
CallSite/InheritRecord) this extractor emits — GraphAssembler resolution
itself is covered separately in test_rust_repo_graph_golden.py.
"""
import pytest

from src.core.extractors.treesitter.rust import RustExtractor

pytestmark = pytest.mark.unit


def _extract(source: str, relative_path: str = "src/lib.rs"):
    return RustExtractor(relative_path).extract(source)


def _by_kind(result, kind):
    return [s for s in result.symbols if s.kind == kind]


# ---------------------------------------------------------------------
# Symbol extraction
# ---------------------------------------------------------------------


def test_struct_enum_trait_extracted_as_own_kinds():
    result = _extract(
        """
        pub struct Animal { name: String }
        pub enum Status { Active, Inactive }
        pub trait Movable { fn move_to(&self, x: i32); }
        """
    )
    assert [s.name for s in _by_kind(result, "STRUCT")] == ["Animal"]
    assert [s.name for s in _by_kind(result, "ENUM")] == ["Status"]
    assert [s.name for s in _by_kind(result, "TRAIT")] == ["Movable"]


def test_trait_signature_only_methods_not_extracted():
    """Mirrors WP-L2's identical decision for TS interface members: no
    acceptance criterion requires extracting trait method declarations
    (no body) as their own METHOD symbols in v1."""
    result = _extract("pub trait Movable { fn move_to(&self, x: i32); }")
    assert _by_kind(result, "METHOD") == []


def test_methods_in_impl_block_become_method_symbols_on_the_type():
    result = _extract(
        """
        pub struct Animal { name: String }
        impl Animal {
            pub fn speak(&self) -> String { self.name.clone() }
            pub fn run(&self) -> i32 { 1 }
        }
        """
    )
    methods = _by_kind(result, "METHOD")
    assert sorted(m.symbol_path for m in methods) == ["Animal.run", "Animal.speak"]
    assert all(m.parent_symbol_path == "Animal" for m in methods)
    assert all(m.metadata["impl_target"] == "Animal" for m in methods)


def test_methods_merge_across_multiple_impl_blocks():
    """Design decision #1: two separate `impl Animal` blocks for the same
    struct produce methods sharing the same symbol_path prefix — the
    merge happens for free via identity (relative_path#Type.method), not
    via any explicit stitching in the extractor."""
    result = _extract(
        """
        pub struct Animal { name: String }
        impl Animal {
            pub fn speak(&self) -> String { self.name.clone() }
        }
        impl Animal {
            pub fn describe(&self) -> String { self.speak() }
        }
        """
    )
    methods = _by_kind(result, "METHOD")
    assert sorted(m.symbol_path for m in methods) == [
        "Animal.describe", "Animal.speak",
    ]


def test_impl_target_generics_and_scoped_path_unwrapped_to_bare_name():
    result = _extract(
        """
        pub struct Container { }
        impl<T> Container {
            pub fn new() -> Self { Container {} }
        }
        """
    )
    methods = _by_kind(result, "METHOD")
    assert [m.symbol_path for m in methods] == ["Container.new"]


def test_free_function_extracted_at_module_scope():
    result = _extract("pub fn helper() -> i32 { 1 }")
    functions = _by_kind(result, "FUNCTION")
    assert [f.symbol_path for f in functions] == ["helper"]
    assert functions[0].parent_symbol_path is None


def test_locally_nested_function_not_extracted():
    """A `fn` defined inside another function's body is an implementation
    detail, not part of the public API surface — v1 does not extract it
    (module docstring)."""
    result = _extract(
        """
        pub fn outer() -> i32 {
            fn inner() -> i32 { 2 }
            inner()
        }
        """
    )
    functions = _by_kind(result, "FUNCTION")
    assert [f.symbol_path for f in functions] == ["outer"]


def test_inline_mod_block_is_transparent_in_v1():
    """v1 design decision: inline `mod name { ... }` blocks are
    transparent — their contents extract as if at file top level."""
    result = _extract(
        """
        mod nested {
            pub fn inner_fn() -> i32 { 1 }
        }
        """
    )
    functions = _by_kind(result, "FUNCTION")
    assert [f.symbol_path for f in functions] == ["inner_fn"]


# ---------------------------------------------------------------------
# Calls
# ---------------------------------------------------------------------


def test_self_receiver_call():
    result = _extract(
        """
        pub struct Animal { name: String }
        impl Animal {
            pub fn speak(&self) -> String { self.name.clone() }
            pub fn describe(&self) -> String { self.speak() }
        }
        """
    )
    calls = [c for c in result.calls if c.callee_name == "speak"]
    assert len(calls) == 1
    assert calls[0].receiver == "self"
    assert calls[0].caller_symbol_path == "Animal.describe"


def test_self_capital_associated_call_rewritten_to_enclosing_type():
    result = _extract(
        """
        pub struct Animal { name: String }
        impl Animal {
            pub fn new() -> Self { Self::build() }
            fn build() -> Self { Animal { name: String::new() } }
        }
        """
    )
    calls = [c for c in result.calls if c.callee_name == "build"]
    assert len(calls) == 1
    assert calls[0].receiver == "Animal"


def test_type_qualified_call():
    result = _extract(
        """
        pub struct Animal { name: String }
        impl Animal {
            pub fn new() -> Self { Animal { name: String::new() } }
        }
        pub fn make() -> Animal { Animal::new() }
        """
    )
    calls = [
        c for c in result.calls
        if c.callee_name == "new" and c.caller_symbol_path == "make"
    ]
    assert len(calls) == 1
    assert calls[0].receiver == "Animal"


def test_bare_call_has_no_receiver():
    result = _extract(
        """
        pub fn helper() -> i32 { 1 }
        pub fn caller() -> i32 { helper() }
        """
    )
    calls = [c for c in result.calls if c.callee_name == "helper"]
    assert len(calls) == 1
    assert calls[0].receiver is None
    assert calls[0].caller_symbol_path == "caller"


# ---------------------------------------------------------------------
# Inherits: `impl Trait for Type`
# ---------------------------------------------------------------------


def test_impl_trait_for_type_emits_inherit_record():
    result = _extract(
        """
        pub struct Animal { name: String }
        pub trait Movable { fn move_to(&self, x: i32); }
        impl Movable for Animal {
            fn move_to(&self, _x: i32) {}
        }
        """
    )
    assert len(result.inherits) == 1
    rec = result.inherits[0]
    assert rec.child_symbol_path == "Animal"
    assert rec.parent_name == "Movable"
    assert rec.kind == "TRAIT_IMPL"


def test_plain_inherent_impl_emits_no_inherit_record():
    result = _extract(
        """
        pub struct Animal { name: String }
        impl Animal { pub fn speak(&self) {} }
        """
    )
    assert result.inherits == []


def test_impl_trait_for_type_methods_use_type_name_not_trait_name():
    result = _extract(
        """
        pub struct Animal { name: String }
        pub trait Movable { fn move_to(&self, x: i32); }
        impl Movable for Animal {
            fn move_to(&self, _x: i32) {}
        }
        """
    )
    methods = _by_kind(result, "METHOD")
    assert [m.symbol_path for m in methods] == ["Animal.move_to"]


# ---------------------------------------------------------------------
# Imports: `use` declarations
# ---------------------------------------------------------------------


def test_use_crate_relative():
    result = _extract("use crate::Animal;")
    assert len(result.imports) == 1
    imp = result.imports[0]
    assert imp.imported_name == "Animal"
    assert imp.raw_module == ""
    assert imp.metadata["level"] == 1


def test_use_self_relative():
    result = _extract("use self::util::helper;")
    assert len(result.imports) == 1
    imp = result.imports[0]
    assert imp.imported_name == "helper"
    assert imp.raw_module == "util"
    assert imp.metadata["level"] == 2


def test_use_super_relative():
    result = _extract("use super::Circle;")
    imp = result.imports[0]
    assert imp.imported_name == "Circle"
    assert imp.raw_module == ""
    assert imp.metadata["level"] == 3


def test_use_double_super():
    result = _extract("use super::super::Circle;")
    imp = result.imports[0]
    assert imp.imported_name == "Circle"
    assert imp.metadata["level"] == 4


def test_use_external_crate_is_bare_passthrough():
    result = _extract("use serde::Deserialize;")
    imp = result.imports[0]
    assert imp.imported_name == "Deserialize"
    assert imp.raw_module == "serde"
    assert imp.metadata["level"] == 0


def test_use_plain_single_segment():
    result = _extract("use plain_crate;")
    imp = result.imports[0]
    assert imp.imported_name is None
    assert imp.raw_module == "plain_crate"


def test_use_grouped_list():
    result = _extract("use std::collections::{HashMap, HashSet};")
    names = sorted(i.imported_name for i in result.imports)
    assert names == ["HashMap", "HashSet"]
    assert all(i.raw_module == "std.collections" for i in result.imports)


def test_use_as_alias():
    result = _extract("use std::fmt::Display as Fmt;")
    imp = result.imports[0]
    assert imp.imported_name == "Display"
    assert imp.alias == "Fmt"


# ---------------------------------------------------------------------
# Macros
# ---------------------------------------------------------------------


def test_macro_invocation_counted_not_extracted_as_call():
    result = _extract(
        """
        pub fn greet() -> String { format!("hi") }
        """
    )
    assert result.calls == []
    functions = _by_kind(result, "FUNCTION")
    assert functions[0].metadata["macro_invocations"] == 1
