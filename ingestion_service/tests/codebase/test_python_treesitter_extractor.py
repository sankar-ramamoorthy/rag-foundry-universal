# ingestion_service/tests/codebase/test_python_treesitter_extractor.py
"""
WP-L5 (issue #134) unit tests for PythonTreeSitterExtractor, mirroring
test_java_extractor.py/test_rust_extractor.py's depth — not the thin
test_python_extractor.py, which only smoke-tests PythonASTExtractor
against its own source file.

Every case here also asserts the SAME assertion against
PythonASTExtractor where the behavior is expected to match (parity), or
notes explicitly where it deliberately doesn't (the syntax-error case).
"""
import pytest

from src.core.extractors.python_extractor import PythonASTExtractor
from src.core.extractors.treesitter.python import PythonTreeSitterExtractor

pytestmark = pytest.mark.unit

REL_PATH = "pkg/mod.py"


def _extract_both(source: str):
    ast_result = PythonASTExtractor(relative_path=REL_PATH).extract(source)
    ts_result = PythonTreeSitterExtractor(relative_path=REL_PATH).extract(source)
    return ast_result, ts_result


def _sym(result, name, kind=None):
    for s in result.symbols:
        if s.name == name and (kind is None or s.kind == kind):
            return s
    raise AssertionError(f"no symbol named {name!r} (kind={kind}) in {result.symbols}")


def test_module_symbol():
    ast_result, ts_result = _extract_both("x = 1\n")
    ast_mod = _sym(ast_result, "pkg.mod", "MODULE")
    ts_mod = _sym(ts_result, "pkg.mod", "MODULE")
    assert ast_mod.symbol_path == ts_mod.symbol_path is None
    assert ast_mod.text == ts_mod.text == "x = 1\n"


def test_top_level_function():
    src = "def top_level(a, b=1):\n    pass\n"
    ast_result, ts_result = _extract_both(src)
    ast_fn = _sym(ast_result, "top_level", "FUNCTION")
    ts_fn = _sym(ts_result, "top_level", "FUNCTION")
    assert ast_fn.symbol_path == ts_fn.symbol_path == "top_level"
    assert ast_fn.parent_symbol_path == ts_fn.parent_symbol_path is None
    assert ast_fn.metadata["args"] == ts_fn.metadata["args"] == ["a", "b"]
    assert ast_fn.metadata["is_async"] == ts_fn.metadata["is_async"] is False
    assert ast_fn.text == ts_fn.text == src.rstrip("\n")


def test_async_function():
    src = "async def fetch(self):\n    pass\n"
    ast_result, ts_result = _extract_both(src)
    ast_fn = _sym(ast_result, "fetch")
    ts_fn = _sym(ts_result, "fetch")
    assert ast_fn.metadata["is_async"] == ts_fn.metadata["is_async"] is True


def test_class_with_bases_and_method():
    src = (
        "class Foo(Base):\n"
        "    def bar(self, x):\n"
        "        return x\n"
    )
    ast_result, ts_result = _extract_both(src)
    ast_cls = _sym(ast_result, "Foo", "CLASS")
    ts_cls = _sym(ts_result, "Foo", "CLASS")
    assert ast_cls.symbol_path == ts_cls.symbol_path == "Foo"
    assert ast_cls.metadata["bases"] == ts_cls.metadata["bases"] == ["Base"]

    ast_method = _sym(ast_result, "bar", "METHOD")
    ts_method = _sym(ts_result, "bar", "METHOD")
    assert ast_method.symbol_path == ts_method.symbol_path == "Foo.bar"
    assert ast_method.parent_symbol_path == ts_method.parent_symbol_path == "Foo"
    assert ast_method.metadata["args"] == ts_method.metadata["args"] == ["self", "x"]


def test_staticmethod_and_classmethod_decorators_still_classify_as_method():
    src = (
        "class Foo:\n"
        "    @staticmethod\n"
        "    def make():\n"
        "        pass\n"
        "\n"
        "    @classmethod\n"
        "    def create(cls):\n"
        "        pass\n"
    )
    ast_result, ts_result = _extract_both(src)
    for name in ("make", "create"):
        ast_m = _sym(ast_result, name, "METHOD")
        ts_m = _sym(ts_result, name, "METHOD")
        assert ast_m.symbol_path == ts_m.symbol_path == f"Foo.{name}"


def test_class_with_metaclass_keyword_argument_excluded_from_bases():
    src = "class Foo(Base, metaclass=Meta):\n    pass\n"
    ast_result, ts_result = _extract_both(src)
    ast_cls = _sym(ast_result, "Foo", "CLASS")
    ts_cls = _sym(ts_result, "Foo", "CLASS")
    assert ast_cls.metadata["bases"] == ts_cls.metadata["bases"] == ["Base"]


def test_nested_class_symbol_path_uses_dot_join():
    src = (
        "class Outer:\n"
        "    class Inner:\n"
        "        def method(self):\n"
        "            pass\n"
    )
    ast_result, ts_result = _extract_both(src)
    ast_inner = _sym(ast_result, "Inner", "CLASS")
    ts_inner = _sym(ts_result, "Inner", "CLASS")
    assert ast_inner.symbol_path == ts_inner.symbol_path == "Outer.Inner"
    assert ast_inner.parent_symbol_path == ts_inner.parent_symbol_path == "Outer"

    # Bug-for-bug parity with PythonASTExtractor (see python.py's module
    # docstring): a nested class's method uses the nearest class
    # ancestor's BARE name for symbol_path, not its full dotted path.
    ast_method = _sym(ast_result, "method", "METHOD")
    ts_method = _sym(ts_result, "method", "METHOD")
    assert ast_method.symbol_path == ts_method.symbol_path == "Inner.method"
    assert (
        ast_method.parent_symbol_path
        == ts_method.parent_symbol_path
        == "Outer.Inner"
    )


def test_imports_absolute_and_aliased():
    src = "import os\nimport os.path as op\n"
    ast_result, ts_result = _extract_both(src)
    ast_keys = {(i.raw_module, i.alias) for i in ast_result.imports}
    ts_keys = {(i.raw_module, i.alias) for i in ts_result.imports}
    assert ast_keys == ts_keys == {("os", None), ("os.path", "op")}


def test_from_import_multiple_names():
    src = "from typing import List, Optional\n"
    ast_result, ts_result = _extract_both(src)
    ast_names = {i.imported_name for i in ast_result.imports}
    ts_names = {i.imported_name for i in ts_result.imports}
    assert ast_names == ts_names == {"List", "Optional"}


def test_relative_imports_level():
    src = "from . import sibling\nfrom ..pkg import thing as t\n"
    ast_result, ts_result = _extract_both(src)
    ast_records = {
        (i.imported_name, i.alias, i.metadata["level"]) for i in ast_result.imports
    }
    ts_records = {
        (i.imported_name, i.alias, i.metadata["level"]) for i in ts_result.imports
    }
    assert ast_records == ts_records == {
        ("sibling", None, 1),
        ("thing", "t", 2),
    }


def test_wildcard_from_import():
    src = "from .pkg2 import *\n"
    ast_result, ts_result = _extract_both(src)
    ast_records = {(i.raw_module, i.imported_name) for i in ast_result.imports}
    ts_records = {(i.raw_module, i.imported_name) for i in ts_result.imports}
    assert ast_records == ts_records == {("pkg2", "*")}


def test_calls_bare_and_attribute_and_self():
    src = (
        "class Foo:\n"
        "    def bar(self, x):\n"
        "        self.baz()\n"
        "        return func(x)\n"
    )
    ast_result, ts_result = _extract_both(src)
    ast_calls = {
        (c.callee_name, c.receiver, c.caller_symbol_path) for c in ast_result.calls
    }
    ts_calls = {
        (c.callee_name, c.receiver, c.caller_symbol_path) for c in ts_result.calls
    }
    assert ast_calls == ts_calls == {
        ("baz", "self", "Foo.bar"),
        ("func", None, "Foo.bar"),
    }


def test_calls_not_emitted_as_symbols():
    src = "def f():\n    g()\n"
    _, ts_result = _extract_both(src)
    assert not any(s.kind == "CALL" for s in ts_result.symbols)


def test_syntax_error_yields_partial_result_not_exception():
    """The one deliberate NON-parity improvement (acceptance criterion):
    PythonASTExtractor raises SyntaxError on a broken file; the
    tree-sitter extractor instead returns what it could parse."""
    src = (
        "def good_before():\n    pass\n\n"
        "def broken(:\n    pass\n\n"
        "def good_after():\n    return 1\n"
    )
    try:
        PythonASTExtractor(relative_path=REL_PATH).extract(src)
        raised = False
    except SyntaxError:
        raised = True
    assert raised, "PythonASTExtractor was expected to raise on this fixture"

    ts_result = PythonTreeSitterExtractor(relative_path=REL_PATH).extract(src)
    names = {s.name for s in ts_result.symbols}
    assert "good_before" in names
    assert "good_after" in names


def test_future_import_is_extracted():
    """`from __future__ import x` is its own tree-sitter grammar rule
    (future_import_statement), distinct from import_from_statement, and
    was initially silently dropped — caught by running the parity
    harness against this repo's own real source files (issue #134)."""
    src = "from __future__ import annotations\n"
    ast_result, ts_result = _extract_both(src)
    ast_recs = {(i.raw_module, i.imported_name) for i in ast_result.imports}
    ts_recs = {(i.raw_module, i.imported_name) for i in ts_result.imports}
    assert ast_recs == ts_recs == {("__future__", "annotations")}


def test_decorator_call_attributed_to_decorated_function():
    """PythonASTExtractor quirk (bug-for-bug parity, see python.py's
    module docstring): a call inside a decorator expression is
    attributed to the function/class it decorates, because
    ast.NodeVisitor visits decorator_list as a field of the
    FunctionDef/ClassDef node itself, after scope_stack has already been
    pushed. tree-sitter's grammar makes `decorator` a SIBLING of the
    definition it decorates, not a child — found via the real-repo
    parity harness run (issue #134)."""
    src = (
        "@app.get(\"/\")\n"
        "def root():\n"
        "    pass\n"
    )
    ast_result, ts_result = _extract_both(src)
    ast_calls = {
        (c.callee_name, c.receiver, c.caller_symbol_path) for c in ast_result.calls
    }
    ts_calls = {
        (c.callee_name, c.receiver, c.caller_symbol_path) for c in ts_result.calls
    }
    assert ast_calls == ts_calls == {("get", "app", "root")}


def test_typed_kwargs_excluded_from_args_like_plain_kwargs():
    """`**fields: Any` wraps its dictionary_splat_pattern inside a
    typed_parameter node — missing the unwrap meant it was misread as a
    plain named parameter literally called "**fields". Found via the
    real-repo parity harness run (issue #134)."""
    src = "def f(trace_id: str, **fields: Any) -> None:\n    pass\n"
    ast_result, ts_result = _extract_both(src)
    ast_fn = _sym(ast_result, "f")
    ts_fn = _sym(ts_result, "f")
    assert ast_fn.metadata["args"] == ts_fn.metadata["args"] == ["trace_id"]


def test_trailing_comment_excluded_from_text_and_span():
    """tree-sitter attaches a trailing same-line comment as the last
    child of the innermost enclosing block, extending that node's (and
    its ancestors') end_byte/end_point to cover it; Python's `ast` has no
    comment nodes at all. Found via the real-repo parity harness run
    (issue #134)."""
    src = "class Foo:\n    x = 1  # trailing comment\n"
    ast_result, ts_result = _extract_both(src)
    ast_cls = _sym(ast_result, "Foo", "CLASS")
    ts_cls = _sym(ts_result, "Foo", "CLASS")
    assert ast_cls.text == ts_cls.text
    assert "# trailing comment" not in ts_cls.text
    assert ast_cls.span == ts_cls.span


def test_span_and_text_match_ast_extractor_exactly():
    src = "class Foo:\n    def bar(self):\n        return 1\n"
    ast_result, ts_result = _extract_both(src)
    for ast_sym, ts_sym in zip(
        sorted(ast_result.symbols, key=lambda s: s.name),
        sorted(ts_result.symbols, key=lambda s: s.name),
    ):
        assert ast_sym.span == ts_sym.span
        assert ast_sym.text == ts_sym.text
