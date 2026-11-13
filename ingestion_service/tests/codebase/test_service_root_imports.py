# ingestion_service/tests/codebase/test_service_root_imports.py
"""
Issue #354 (ADR-032 amendment 2026-11-12): absolute Python imports written
against a service's own root (`from src.core.config import get_settings`
inside `svc_a/src/...`) resolve to that service's module, only when the
repository-root interpretation misses, and never into a sibling service.
"""

from uuid import uuid4

import pytest

from src.core.codebase.repo_graph_builder import RepoGraphBuilder

pytestmark = pytest.mark.unit

CONFIG = "def get_settings():\n    return {}\n"


def _w(root, rel, text=""):
    path = root / rel
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def _write_repo(root):
    # Two services with identical module paths; different marker files.
    _w(root, "svc_a/pyproject.toml", "[project]\nname = 'a'\n")
    _w(root, "svc_b/pytest.ini", "[pytest]\n")
    for svc in ("svc_a", "svc_b"):
        _w(root, f"{svc}/src/core/config.py", CONFIG)
    _w(root, "svc_b/src/only_in_b.py", "def thing():\n    return 1\n")
    _w(
        root,
        "svc_a/src/api/routes.py",
        "import asyncio\n"
        "import fastapi\n"
        "from httpx import AsyncClient\n"
        "from src.core.config import get_settings\n"
        "from src.only_in_b import thing\n"
        "from svc_a.src.core.config import get_settings as gs_full\n"
        "import src.core.config\n"
        "from ..core.config import get_settings as gs_rel\n"
        "\n"
        "def handler():\n"
        "    get_settings()\n"
        "    gs_full()\n"
        "    gs_rel()\n"
        "    src.core.config.get_settings()\n"
        "    thing()\n"
        "    AsyncClient()\n"
        "    fastapi.HTTPException()\n"
        "    return asyncio.to_thread(get_settings)\n",
    )
    _w(
        root,
        "svc_b/src/api/routes.py",
        "from src.core.config import get_settings\n"
        "\n"
        "def handler():\n"
        "    return get_settings()\n",
    )
    _w(
        root,
        "svc_a/tests/test_config.py",
        "from src.core.config import get_settings\n"
        "\n"
        "def test_it():\n"
        "    assert get_settings() == {}\n",
    )
    # Nested project: its own root wins over the enclosing service's.
    _w(root, "svc_a/plugins/p/setup.cfg", "[metadata]\nname = p\n")
    _w(root, "svc_a/plugins/p/src/core/config.py", CONFIG)
    _w(
        root,
        "svc_a/plugins/p/src/run.py",
        "from src.core.config import get_settings\n"
        "\n"
        "def run():\n"
        "    return get_settings()\n",
    )
    # No project marker on the way to the repository root: unresolved.
    _w(
        root,
        "scripts/tool.py",
        "from src.core.config import get_settings\n"
        "\n"
        "def main():\n"
        "    return get_settings()\n",
    )
    # A TypeScript file inside a Python project is unaffected.
    _w(root, "svc_a/web/util.ts", "export function u() { return 1; }\n")
    _w(
        root,
        "svc_a/web/app.ts",
        "import { u } from './util';\nexport function main() { return u(); }\n",
    )


def _build(root, python_roots=True, monkeypatch=None):
    if not python_roots:
        monkeypatch.setattr(
            RepoGraphBuilder, "_discover_python_project_roots", lambda self: ()
        )
    return RepoGraphBuilder(root, ingestion_id=str(uuid4())).build()


@pytest.fixture()
def repo(tmp_path):
    _write_repo(tmp_path)
    return tmp_path


@pytest.fixture()
def graph(repo):
    return _build(repo)


def _targets(graph, from_cid, rel="CALL"):
    return {
        r["to_canonical_id"]
        for r in graph.relationships
        if r["relation_type"] == rel and r["from_canonical_id"] == from_cid
    }


def _edge(graph, from_cid, to_cid, rel="CALL"):
    hits = [
        r
        for r in graph.relationships
        if r["relation_type"] == rel
        and r["from_canonical_id"] == from_cid
        and r["to_canonical_id"] == to_cid
    ]
    assert len(hits) <= 1
    return hits[0] if hits else None


A_HANDLER = "svc_a/src/api/routes.py#handler"
A_CONFIG = "svc_a/src/core/config.py"


def test_project_roots_are_marker_directories_excluding_repo_root(repo):
    _w(repo, "pyproject.toml", "[project]\nname = 'root'\n")
    roots = RepoGraphBuilder(repo, ingestion_id="x")._discover_python_project_roots()
    assert roots == ("svc_a", "svc_a/plugins/p", "svc_b")


def test_each_service_resolves_to_its_own_module(graph):
    edge = _edge(graph, A_HANDLER, f"{A_CONFIG}#get_settings")
    assert edge is not None
    assert edge["relationship_metadata"]["confidence"] == 1.0
    assert _edge(
        graph,
        "svc_b/src/api/routes.py#handler",
        "svc_b/src/core/config.py#get_settings",
    )
    assert _edge(graph, "svc_a/src/api/routes.py", A_CONFIG, rel="IMPORTS")


def test_never_resolves_into_a_sibling_service(graph):
    targets = _targets(graph, A_HANDLER)
    assert not any(t.startswith("svc_b/") for t in targets)
    assert "EXTERNAL_SYMBOL:src.only_in_b.thing" in targets


def test_both_spellings_and_relative_import_reach_the_same_node(graph):
    targets = _targets(graph, A_HANDLER)
    # get_settings, gs_full (repo-root spelling), gs_rel (relative) and the
    # dotted module receiver all collapse onto the one real definition.
    assert f"{A_CONFIG}#get_settings" in targets
    assert not any(
        t.startswith("EXTERNAL_SYMBOL:") and t.endswith("get_settings") for t in targets
    )
    edge = _edge(graph, A_HANDLER, f"{A_CONFIG}#get_settings")
    assert len(edge["relationship_metadata"]["call_sites"]) == 4


def test_external_imports_stay_external(graph):
    targets = _targets(graph, A_HANDLER)
    assert "EXTERNAL_SYMBOL:httpx.AsyncClient" in targets
    assert "EXTERNAL_SYMBOL:fastapi.HTTPException" in targets
    assert "EXTERNAL_SYMBOL:asyncio.to_thread" in targets
    assert "EXTERNAL_MODULE:fastapi" in _targets(
        graph, "svc_a/src/api/routes.py", rel="IMPORTS"
    )


def test_tests_directory_resolves_into_its_service(graph):
    assert _edge(
        graph, "svc_a/tests/test_config.py#test_it", f"{A_CONFIG}#get_settings"
    )


def test_nearest_nested_project_root_wins(graph):
    assert _edge(
        graph,
        "svc_a/plugins/p/src/run.py#run",
        "svc_a/plugins/p/src/core/config.py#get_settings",
    )


def test_file_outside_any_project_stays_unresolved(graph):
    assert _targets(graph, "scripts/tool.py#main") == {
        "EXTERNAL_SYMBOL:src.core.config.get_settings"
    }


def test_repository_root_interpretation_keeps_precedence(repo):
    """Ambiguity rule: a repo-root `src` package wins, exactly as before."""
    _w(repo, "src/core/config.py", CONFIG)
    graph = _build(repo)
    assert _edge(graph, A_HANDLER, "src/core/config.py#get_settings")
    assert _edge(
        graph, "svc_b/src/api/routes.py#handler", "src/core/config.py#get_settings"
    )


def test_rust_without_cargo_toml_keeps_its_convention(tmp_path, monkeypatch):
    """Review fix: Python markers must not drop the default Rust convention
    for a repository with `.rs` files but no Cargo.toml."""
    _w(tmp_path, "svc/pytest.ini", "[pytest]\n")
    _w(tmp_path, "util.rs", "pub fn helper() -> i32 { 1 }\n")
    # A `use crate::` import cannot fall back to unique-global-name lookup,
    # so it only resolves if the Rust convention is present.
    _w(
        tmp_path,
        "main.rs",
        "mod util;\nuse crate::util::helper;\nfn run() -> i32 { helper() }\n",
    )
    graph = _build(tmp_path)
    with monkeypatch.context() as m:
        before = _build(tmp_path, python_roots=False, monkeypatch=m)

    def rust_edges(g):
        return {
            (r["from_canonical_id"], r["to_canonical_id"], r["relation_type"])
            for r in g.relationships
            if r["from_canonical_id"].endswith(".rs")
            or ".rs#" in r["from_canonical_id"]
        }

    assert rust_edges(graph) == rust_edges(before)
    assert ("main.rs#run", "util.rs#helper", "CALL") in rust_edges(graph)
    assert ("main.rs", "util.rs", "IMPORTS") in rust_edges(graph)


def test_ids_stable_and_no_existing_edge_lost_or_retargeted(repo, monkeypatch):
    graph = _build(repo)
    with monkeypatch.context() as m:
        before = _build(repo, python_roots=False, monkeypatch=m)

    def ids(g):
        return {e["canonical_id"] for e in g.all_entities()}

    def edges(g):
        return {
            (r["from_canonical_id"], r["to_canonical_id"], r["relation_type"])
            for r in g.relationships
        }

    # Only placeholder nodes may disappear; no node id appears or changes.
    assert ids(graph) <= ids(before)
    assert all(i.startswith("EXTERNAL_") for i in ids(before) - ids(graph))
    # Every edge to a real node survives unchanged; only edges into
    # placeholders may be replaced.
    lost = edges(before) - edges(graph)
    assert lost and all(t.startswith("EXTERNAL_") for _, t, _ in lost)
    # Every new edge replaces a placeholder for the same symbol name.
    for frm, to, rel in edges(graph) - edges(before):
        name = to.rsplit("#", 1)[-1].rsplit(".", 1)[-1]
        if rel == "IMPORTS":
            assert any(
                f == frm and r == "IMPORTS" and t.startswith("EXTERNAL_MODULE:")
                for f, t, r in lost
            )
            continue
        assert any(
            f == frm and r == rel and t.rsplit(".", 1)[-1] == name for f, t, r in lost
        ), (frm, to, rel)
    # TypeScript resolution unchanged.
    assert _edge(graph, "svc_a/web/app.ts#main", "svc_a/web/util.ts#u")
