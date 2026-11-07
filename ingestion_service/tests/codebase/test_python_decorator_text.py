# ingestion_service/tests/codebase/test_python_decorator_text.py
"""
Issue #311 (Phase 3, WP-L5 Python parity): a decorated Python definition's
stored text must include its decorator lines. Found when 3 of the 5 pypa/hatch
manifest functions (click commands) hashed differently from the pinned source:
stored text started at `def`, the manifest source at the first `@decorator`.

Every case runs against BOTH extractors (tree-sitter and the stdlib-ast
fallback) and checks the text byte-for-byte against the source slice, not just
that decorator names appear somewhere in it.

Identity/graph stability is guarded too: kind, name, symbol_path, parent and
span are not allowed to move as a side effect of the text fix.
"""
import pytest

from src.core.extractors.python_extractor import PythonASTExtractor
from src.core.extractors.treesitter.python import PythonTreeSitterExtractor

pytestmark = pytest.mark.unit

REL_PATH = "pkg/mod.py"

EXTRACTORS = [
    pytest.param(PythonTreeSitterExtractor, id="treesitter"),
    pytest.param(PythonASTExtractor, id="ast"),
]


def _sym(result, name, kind=None):
    for s in result.symbols:
        if s.name == name and (kind is None or s.kind == kind):
            return s
    raise AssertionError(f"no symbol {name!r} ({kind}) in {result.symbols}")


# Exact slice the symbol text must equal (first '@' line through last body line).
SIMPLE = (
    "@click.command()\n"
    "@click.pass_obj\n"
    "def hello(app):\n"
    '    return "hi"\n'
)

MULTILINE = (
    '@click.command(short_help="Generate lockfiles")\n'
    '@click.option("--upgrade", "-U", is_flag=True, help="Upgrade all packages")\n'
    "@click.option(\n"
    '    "--export-all",\n'
    '    "export_all_path",\n'
    "    type=click.Path(),\n"
    "    default=None,\n"
    ")\n"
    "@click.pass_obj\n"
    "def lock(\n"
    "    app,\n"
    "    upgrade,\n"
    "    export_all_path,\n"
    "):\n"
    "    if upgrade:\n"
    "        app.upgrade()\n"
    "    return export_all_path\n"
)

PREFIX = "import click\n\nX = 1\n\n"
SUFFIX = "\n\ndef after():\n    pass\n"


@pytest.mark.parametrize("extractor_cls", EXTRACTORS)
@pytest.mark.parametrize(
    "name,expected",
    [("hello", SIMPLE), ("lock", MULTILINE)],
    ids=["ordinary", "multiline"],
)
def test_decorated_function_text_is_exact_source_slice(extractor_cls, name, expected):
    # A definition's text runs from its first '@' to its last token (no
    # trailing newline), exactly as in the pinned manifest source.
    expected = expected.rstrip("\n")
    src = PREFIX + expected + SUFFIX
    assert src.count(expected) == 1  # the expected slice is unambiguous
    fn = _sym(extractor_cls(relative_path=REL_PATH).extract(src), name, "FUNCTION")
    assert fn.text == expected


@pytest.mark.parametrize("extractor_cls", EXTRACTORS)
def test_decorated_method_text_includes_decorators(extractor_cls):
    src = (
        "class C:\n"
        "    @staticmethod\n"
        "    @other(\n"
        "        1,\n"
        "    )\n"
        "    def m(x):\n"
        "        return x\n"
    )
    expected = (
        "@staticmethod\n"
        "    @other(\n"
        "        1,\n"
        "    )\n"
        "    def m(x):\n"
        "        return x"
    )
    # Starts at the first '@' (its leading indent is outside the node, as for
    # undecorated nested defs) and ends at the last body token.
    m = _sym(extractor_cls(relative_path=REL_PATH).extract(src), "m", "METHOD")
    assert m.text == expected
    assert m.symbol_path == "C.m"


@pytest.mark.parametrize("extractor_cls", EXTRACTORS)
def test_decorated_class_text_includes_decorators(extractor_cls):
    src = "@dataclass(frozen=True)\nclass P:\n    x: int = 0\n"
    cls = _sym(extractor_cls(relative_path=REL_PATH).extract(src), "P", "CLASS")
    assert cls.text == "@dataclass(frozen=True)\nclass P:\n    x: int = 0"


@pytest.mark.parametrize("extractor_cls", EXTRACTORS)
def test_undecorated_function_text_unchanged(extractor_cls):
    src = "# lead\n\ndef plain(a):\n    return a\n"
    fn = _sym(extractor_cls(relative_path=REL_PATH).extract(src), "plain", "FUNCTION")
    assert fn.text == "def plain(a):\n    return a"


@pytest.mark.parametrize("extractor_cls", EXTRACTORS)
def test_comment_between_decorator_and_def_is_kept(extractor_cls):
    src = "@d\n# why\ndef f():\n    pass\n"
    fn = _sym(extractor_cls(relative_path=REL_PATH).extract(src), "f", "FUNCTION")
    assert fn.text == "@d\n# why\ndef f():\n    pass"


@pytest.mark.parametrize("extractor_cls", EXTRACTORS)
def test_identity_and_span_unchanged_by_decorators(extractor_cls):
    """Canonical-ID inputs and the span stay those of the `def` itself."""
    fn = _sym(
        extractor_cls(relative_path=REL_PATH).extract(PREFIX + SIMPLE + SUFFIX),
        "hello",
        "FUNCTION",
    )
    def_line = PREFIX.count("\n") + 3  # 1-based line of `def hello`
    assert (fn.kind, fn.name, fn.symbol_path, fn.parent_symbol_path) == (
        "FUNCTION",
        "hello",
        "hello",
        None,
    )
    assert fn.span == (def_line, def_line + 1)
    assert fn.metadata["lineno"] == def_line


def test_both_extractors_agree_on_decorated_text():
    src = PREFIX + MULTILINE + SUFFIX
    ts = _sym(PythonTreeSitterExtractor(relative_path=REL_PATH).extract(src), "lock")
    ast_ = _sym(PythonASTExtractor(relative_path=REL_PATH).extract(src), "lock")
    assert ts.text == ast_.text == MULTILINE.rstrip("\n")
