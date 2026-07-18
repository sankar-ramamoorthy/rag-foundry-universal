# ingestion_service/tests/codebase/test_extractor_fixes.py
"""
F-05: module names must strip the ".py" suffix, not the {., p, y} char set.
F-01: async defs must produce FUNCTION/METHOD artifacts like sync defs.
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
    artifacts = PythonASTExtractor(relative_path="happy.py").extract("x = 1\n")
    module = next(a for a in artifacts if a["artifact_type"] == "MODULE")
    assert module["name"] == "happy"
    assert module["id"] == "happy.py"  # canonical id unchanged (ADR-031)


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
def async_artifacts():
    return PythonASTExtractor(relative_path="app.py").extract(ASYNC_SOURCE)


def test_async_function_produces_artifact(async_artifacts):
    funcs = {
        a["id"]: a for a in async_artifacts
        if a["artifact_type"] in ("FUNCTION", "METHOD")
    }
    assert "app.py#main" in funcs, "async def main is invisible (F-01)"
    assert funcs["app.py#main"]["artifact_type"] == "FUNCTION"
    assert funcs["app.py#main"]["metadata"]["is_async"] is True


def test_async_method_produces_method_artifact(async_artifacts):
    funcs = {
        a["id"]: a for a in async_artifacts
        if a["artifact_type"] in ("FUNCTION", "METHOD")
    }
    assert "app.py#Handler.handle" in funcs
    assert funcs["app.py#Handler.handle"]["artifact_type"] == "METHOD"
    assert funcs["app.py#Handler.handle"]["metadata"]["is_async"] is True


def test_sync_defs_marked_not_async(async_artifacts):
    funcs = {
        a["id"]: a for a in async_artifacts
        if a["artifact_type"] in ("FUNCTION", "METHOD")
    }
    assert funcs["app.py#helper"]["metadata"]["is_async"] is False
    assert funcs["app.py#Handler.load"]["metadata"]["is_async"] is False


def test_calls_inside_async_body_attributed_to_async_def(async_artifacts):
    """Before F-01 the CALL inside `async def main` had the MODULE as its
    parent — mis-attributing the caller."""
    calls = {
        a["name"]: a for a in async_artifacts
        if a["artifact_type"] == "CALL"
    }
    assert calls["helper"]["parent_id"] == "app.py#main"
    assert calls["self.load"]["parent_id"] == "app.py#Handler.handle"


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
