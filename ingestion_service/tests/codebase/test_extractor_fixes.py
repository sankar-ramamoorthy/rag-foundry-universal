# ingestion_service/tests/codebase/test_extractor_fixes.py
"""
F-05: module names must strip the ".py" suffix, not the {., p, y} char set.
F-01: async defs must produce FUNCTION/METHOD symbols like sync defs.
"""
import pytest
from uuid import uuid4

from src.core.codebase.repo_graph_builder import RepoGraphBuilder
from src.core.extractors.python_extractor import PythonASTExtractor

pytestmark = pytest.mark.unit


# -----------------------------
# F-05 — module naming
# -----------------------------

@pytest.mark.parametrize(
    "relative_path, expected_module_name",
    [
        ("happy.py", "happy"),                 # was "ha"
        ("utils/copy.py", "utils.copy"),       # was "utils.co"
        ("spy.py", "spy"),                     # was "s"
        ("pkg/sub/mod.py", "pkg.sub.mod"),
        ("app/service.py", "app.service"),
        ("proxy.py", "proxy"),                 # was "prox"
    ],
)
def test_module_name_strips_suffix_not_charset(
    relative_path, expected_module_name
):
    extractor = PythonASTExtractor(relative_path=relative_path)
    assert extractor.module_name == expected_module_name


def test_module_artifact_carries_fixed_name():
    result = PythonASTExtractor(relative_path="happy.py").extract("x = 1\n")
    module = next(s for s in result.symbols if s.kind == "MODULE")
    assert module.name == "happy"


# -----------------------------
# F-01 — async defs
# -----------------------------

ASYNC_SOURCE = (
    "class Handler:\n"
    "    async def handle(self):\n"
    "        return await self.load()\n"
    "\n"
    "    def load(self):\n"
    "        return 1\n"
    "\n"
    "\n"
    "async def main():\n"
    "    helper()\n"
    "\n"
    "\n"
    "def helper():\n"
    "    return 2\n"
)


@pytest.fixture()
def async_symbols():
    return PythonASTExtractor(relative_path="app.py").extract(ASYNC_SOURCE).symbols


def test_async_function_produces_artifact(async_symbols):
    funcs = {
        s.symbol_path: s for s in async_symbols
        if s.kind in ("FUNCTION", "METHOD")
    }
    assert "main" in funcs, "async def main is invisible (F-01)"
    assert funcs["main"].kind == "FUNCTION"
    assert funcs["main"].metadata["is_async"] is True


def test_async_method_produces_method_artifact(async_symbols):
    funcs = {
        s.symbol_path: s for s in async_symbols
        if s.kind in ("FUNCTION", "METHOD")
    }
    assert "Handler.handle" in funcs
    assert funcs["Handler.handle"].kind == "METHOD"
    assert funcs["Handler.handle"].metadata["is_async"] is True


def test_sync_defs_marked_not_async(async_symbols):
    funcs = {
        s.symbol_path: s for s in async_symbols
        if s.kind in ("FUNCTION", "METHOD")
    }
    assert funcs["helper"].metadata["is_async"] is False
    assert funcs["Handler.load"].metadata["is_async"] is False


def test_calls_inside_async_body_attributed_to_async_def():
    """Before F-01 the call site inside `async def main` had the MODULE as
    its parent — mis-attributing the caller. F-03: call sites live in the
    extractor's side list with the receiver split from the name."""
    extractor = PythonASTExtractor(relative_path="app.py")
    extractor.extract(ASYNC_SOURCE)
    sites = {
        (s.receiver, s.callee_name): s for s in extractor.call_sites
    }
    assert sites[(None, "helper")].caller_symbol_path == "main"
    assert sites[("self", "load")].caller_symbol_path == "Handler.handle"


def test_async_def_end_to_end_through_graph_builder(tmp_path):
    """Async artifacts must flow through the full build: entity present,
    text extracted from the `async def` line, DEFINES edge created."""
    (tmp_path / "app.py").write_text(ASYNC_SOURCE, encoding="utf-8")
    graph = RepoGraphBuilder(tmp_path, ingestion_id=str(uuid4())).build()

    entity = graph.entities.get("app.py#main")
    assert entity is not None
    assert entity["text"].startswith("async def main():")

    method = graph.entities.get("app.py#Handler.handle")
    assert method is not None
    assert method["text"].startswith("async def handle(self):")

    defines = {
        (r["from_canonical_id"], r["to_canonical_id"])
        for r in graph.relationships
        if r["relation_type"] == "DEFINES"
    }
    assert ("app.py", "app.py#main") in defines
    assert ("app.py#Handler", "app.py#Handler.handle") in defines
