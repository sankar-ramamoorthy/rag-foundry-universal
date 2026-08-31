# ingestion_service/tests/codebase/test_typescript_extractor.py
"""
TypeScriptExtractor unit tests (WP-L2). Mirrors test_python_extractor.py's
style: inline source snippets, no DB/Docker, asserting directly on the IR
(SymbolRecord/ImportRecord/CallSite) this extractor emits — GraphAssembler
resolution itself is covered separately in test_ts_repo_graph_golden.py.
"""
import pytest

from src.core.extractors.treesitter.typescript import TypeScriptExtractor
from src.core.codebase.module_conventions import TypeScriptModuleConvention

pytestmark = pytest.mark.unit


def _extract(source: str, relative_path: str = "src/sample.ts"):
    return TypeScriptExtractor(relative_path).extract(source)


def _by_kind(result, kind):
    return [s for s in result.symbols if s.kind == kind]


# ---------------------------------------------------------------------
# Symbol extraction (spec User Story 1)
# ---------------------------------------------------------------------


def test_class_and_methods_extracted():
    result = _extract(
        """
        export class Animal {
          speak() { return "hi"; }
          run() { return 1; }
        }
        """
    )
    classes = _by_kind(result, "CLASS")
    methods = _by_kind(result, "METHOD")
    assert [c.name for c in classes] == ["Animal"]
    assert sorted(m.symbol_path for m in methods) == ["Animal.run", "Animal.speak"]
    assert all(m.parent_symbol_path == "Animal" for m in methods)


def test_interface_extracted_as_own_kind():
    result = _extract("export interface Movable { move(): void; }")
    interfaces = _by_kind(result, "INTERFACE")
    assert [i.name for i in interfaces] == ["Movable"]
    # interface members are not extracted as METHOD symbols in v1
    # (spec.md Assumptions) — only the interface node itself exists.
    assert _by_kind(result, "METHOD") == []


def test_top_level_function_extracted():
    result = _extract("export function topFn() { return 1; }")
    functions = _by_kind(result, "FUNCTION")
    assert [f.symbol_path for f in functions] == ["topFn"]


def test_named_const_arrow_and_function_expression_are_functions():
    result = _extract(
        """
        const arrowFn = () => { return 1; };
        const funcExprFn = function() { return 2; };
        """
    )
    functions = {f.symbol_path for f in _by_kind(result, "FUNCTION")}
    assert functions == {"arrowFn", "funcExprFn"}


def test_class_property_arrow_is_a_method():
    result = _extract(
        """
        export class Widget {
          onClick = () => { return 1; };
        }
        """
    )
    methods = _by_kind(result, "METHOD")
    assert [m.symbol_path for m in methods] == ["Widget.onClick"]


def test_anonymous_callback_is_not_a_symbol_but_is_counted():
    result = _extract(
        """
        export function run() {
          setTimeout(() => { console.log("anon"); }, 1);
        }
        """
    )
    functions = _by_kind(result, "FUNCTION")
    assert [f.symbol_path for f in functions] == ["run"]
    assert functions[0].metadata["anonymous_functions_skipped"] == 1


def test_anonymous_callback_at_module_scope_counts_on_module_symbol():
    result = _extract("setTimeout(() => { console.log('x'); }, 1);")
    module = _by_kind(result, "MODULE")[0]
    assert module.metadata.get("anonymous_functions_skipped") == 1


def test_default_export_function_gets_synthesized_default_symbol_path():
    result = _extract(
        "export default function subDefault() { return 1; }",
        relative_path="src/sub/index.ts",
    )
    functions = _by_kind(result, "FUNCTION")
    assert len(functions) == 1
    assert functions[0].name == "default"
    assert functions[0].symbol_path == "default"
    assert functions[0].metadata["declared_name"] == "subDefault"
    assert functions[0].metadata["default_export"] is True


def test_async_function_flagged():
    result = _extract("export async function fetchIt() { return 1; }")
    functions = _by_kind(result, "FUNCTION")
    assert functions[0].metadata["is_async"] is True


def test_jsx_file_parses_under_tsx_grammar():
    result = _extract(
        "export function Widget() { return <div>hi</div>; }",
        relative_path="src/widget.tsx",
    )
    assert [f.symbol_path for f in _by_kind(result, "FUNCTION")] == ["Widget"]


# ---------------------------------------------------------------------
# Import extraction (spec User Story 2 / data-model.md's ImportRecord table)
# ---------------------------------------------------------------------


def test_named_import():
    result = _extract('import { helper } from "./util";')
    assert len(result.imports) == 1
    imp = result.imports[0]
    assert (imp.raw_module, imp.imported_name, imp.alias) == ("./util", "helper", None)


def test_named_import_with_alias():
    result = _extract('import { helper as h } from "./util";')
    imp = result.imports[0]
    assert (imp.raw_module, imp.imported_name, imp.alias) == ("./util", "helper", "h")


def test_default_import():
    result = _extract('import Default from "./sub";')
    imp = result.imports[0]
    expected = ("./sub", "default", "Default")
    assert (imp.raw_module, imp.imported_name, imp.alias) == expected


def test_namespace_import():
    result = _extract('import * as ns from "./mod";')
    imp = result.imports[0]
    assert (imp.raw_module, imp.imported_name, imp.alias) == ("./mod", "*", "ns")


def test_side_effect_import():
    result = _extract('import "./side";')
    imp = result.imports[0]
    assert (imp.raw_module, imp.imported_name, imp.alias) == ("./side", "*", None)


def test_reexport_from():
    result = _extract('export { helper } from "./util";')
    imp = result.imports[0]
    assert (imp.raw_module, imp.imported_name, imp.alias) == ("./util", "helper", None)


def test_export_star_from():
    result = _extract('export * from "./all";')
    imp = result.imports[0]
    assert (imp.raw_module, imp.imported_name, imp.alias) == ("./all", "*", None)


def test_export_without_source_is_not_an_import():
    result = _extract("export class Foo {}")
    assert result.imports == []


def test_require_destructured():
    result = _extract('const { a, b: c } = require("./util");')
    records = {(i.imported_name, i.alias) for i in result.imports}
    assert records == {("a", None), ("b", "c")}
    assert all(i.raw_module == "./util" for i in result.imports)


def test_require_whole_module():
    result = _extract('const utils = require("./util");')
    imp = result.imports[0]
    assert (imp.raw_module, imp.imported_name, imp.alias) == ("./util", "*", "utils")


def test_require_side_effect():
    result = _extract('require("./init");')
    imp = result.imports[0]
    assert (imp.raw_module, imp.imported_name, imp.alias) == ("./init", "*", None)


# ---------------------------------------------------------------------
# Call-site extraction (spec User Story 3)
# ---------------------------------------------------------------------


def test_bare_call():
    result = _extract("export function run() { helper(); }")
    call = result.calls[0]
    assert (call.callee_name, call.receiver) == ("helper", None)


def test_this_qualified_call():
    result = _extract(
        """
        export class Dog {
          move() { this.speak(); }
        }
        """
    )
    call = [c for c in result.calls if c.callee_name == "speak"][0]
    assert call.receiver == "this"
    assert call.caller_symbol_path == "Dog.move"


def test_member_call_receiver_captured():
    result = _extract("export function run() { console.log('hi'); }")
    call = result.calls[0]
    assert (call.callee_name, call.receiver) == ("log", "console")


def test_require_call_is_not_also_emitted_as_a_call_site():
    result = _extract('const { a } = require("./util");')
    assert result.calls == []


# ---------------------------------------------------------------------
# extends / implements -> metadata.bases (spec User Story 3)
# ---------------------------------------------------------------------


def test_class_extends_and_implements_recorded_as_bases():
    result = _extract(
        """
        export class Dog extends Animal implements Movable, Runnable {
          move() {}
        }
        """
    )
    cls = _by_kind(result, "CLASS")[0]
    assert cls.metadata["bases"] == ["Animal", "Movable", "Runnable"]


def test_interface_extends_recorded_as_bases():
    result = _extract("export interface Named extends Titled, Other {}")
    iface = _by_kind(result, "INTERFACE")[0]
    assert iface.metadata["bases"] == ["Titled", "Other"]


def test_generic_base_strips_type_arguments():
    result = _extract("export class Foo extends Base<T> implements A<X> {}")
    cls = _by_kind(result, "CLASS")[0]
    assert cls.metadata["bases"] == ["Base", "A"]


# ---------------------------------------------------------------------
# Malformed source (spec Edge Cases)
# ---------------------------------------------------------------------


def test_malformed_source_raises_so_the_file_is_skipped_by_the_builder():
    with pytest.raises(ValueError):
        _extract("class Foo { ( } }} export function")


# ---------------------------------------------------------------------
# JS grammar variant (field_definition vs public_field_definition, no
# interface_declaration)
# ---------------------------------------------------------------------


def test_js_class_property_arrow_and_extends():
    result = _extract(
        """
        class Dog extends Animal {
          move = () => { this.speak(); };
        }
        """,
        relative_path="src/dog.js",
    )
    cls = _by_kind(result, "CLASS")[0]
    assert cls.metadata["bases"] == ["Animal"]
    methods = _by_kind(result, "METHOD")
    assert [m.symbol_path for m in methods] == ["Dog.move"]


# ---------------------------------------------------------------------
# TypeScriptModuleConvention (spec FR-004/FR-005)
# ---------------------------------------------------------------------


def test_module_convention_resolves_relative_specifier():
    convention = TypeScriptModuleConvention()
    assert convention.absolute_import_base("src/index.ts", "./util", 0) == "src/util"


def test_module_convention_resolves_directory_import_to_index():
    convention = TypeScriptModuleConvention()
    assert convention.absolute_import_base("src/index.ts", "./sub", 0) == "src/sub"
    assert convention.dotted_path("src/sub/index.ts") == "src/sub"


def test_module_convention_resolves_parent_relative_specifier():
    convention = TypeScriptModuleConvention()
    assert (
        convention.absolute_import_base("src/nested/a.ts", "../util", 0)
        == "src/util"
    )


def test_module_convention_leaves_bare_specifier_unchanged():
    convention = TypeScriptModuleConvention()
    assert convention.absolute_import_base("src/index.ts", "react", 0) == "react"


def test_module_convention_dotted_path_none_for_non_ts_file():
    convention = TypeScriptModuleConvention()
    assert convention.dotted_path("src/main.py") is None
