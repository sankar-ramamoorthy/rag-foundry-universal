# ingestion_service/tests/codebase/test_repo_graph_builder.py
"""
RepoGraphBuilder tests.

F-03 (WP-G3): call sites are evidence records, not identity-bearing
artifacts — CALL never appears in graph.entities; callers/callees are
linked by aggregated CALL edges carrying call-site linenos and a count.
"""
import pytest
from pathlib import Path
from uuid import uuid4

from src.core.codebase.repo_graph_builder import RepoGraphBuilder
from src.core.codebase.symbol_table import build_symbol_table

pytestmark = pytest.mark.unit


# ---------------------------------------------------------------------
# Smoke tests over this service's own src tree
# ---------------------------------------------------------------------

@pytest.fixture(scope="module")
def repo_graph():
    """Build the repo graph once for the whole test module."""
    ingestion_id = uuid4()
    repo_root = Path(__file__).resolve().parent.parent.parent / "src"
    builder = RepoGraphBuilder(repo_root, ingestion_id=ingestion_id)
    return builder.build()


@pytest.fixture(scope="module")
def symbol_table(repo_graph):
    return build_symbol_table(repo_graph)


def test_total_artifacts(repo_graph):
    assert len(repo_graph.entities) > 0, "No artifacts were collected"


def test_modules_and_classes_collected(repo_graph):
    modules = [a for a in repo_graph.all_entities() if a["artifact_type"] == "MODULE"]
    classes = [a for a in repo_graph.all_entities() if a["artifact_type"] == "CLASS"]
    assert modules, "No MODULE artifacts collected"
    assert classes, "No CLASS artifacts collected"


def test_functions_and_methods_collected(repo_graph):
    funcs = [
        a for a in repo_graph.all_entities()
        if a["artifact_type"] in ("FUNCTION", "METHOD")
    ]
    assert funcs, "No FUNCTION or METHOD artifacts collected"


def test_imports_collected(repo_graph):
    imports = [a for a in repo_graph.all_entities() if a["artifact_type"] == "IMPORT"]
    assert imports, "No IMPORT artifacts collected"


def test_no_call_entities_in_graph(repo_graph):
    """F-03: CALL is not an identity-bearing artifact — zero CALL entities."""
    calls = [a for a in repo_graph.all_entities() if a["artifact_type"] == "CALL"]
    assert calls == [], "CALL artifacts must not enter the identity space"


def test_call_sites_collected_as_evidence(repo_graph):
    """The evidence side-list replaces CALL artifacts."""
    assert repo_graph.call_sites, "No call sites collected"
    for site in repo_graph.call_sites[:50]:
        assert "name" in site
        assert "receiver" in site
        assert site.get("parent_id") is not None
        assert isinstance(site.get("lineno"), int)


def test_call_edges_reference_known_entities(repo_graph):
    call_edges = [
        r for r in repo_graph.relationships if r["relation_type"] == "CALL"
    ]
    assert call_edges, "No CALL edges produced"
    for edge in call_edges:
        assert edge["from_canonical_id"] in repo_graph.entities
        assert edge["to_canonical_id"] in repo_graph.entities
        meta = edge["relationship_metadata"]
        assert 0.0 <= meta["confidence"] <= 1.0
        assert meta["count"] == len(meta["call_sites"]) >= 1


def test_defines_edges_reference_known_entities(repo_graph):
    defines = [
        r for r in repo_graph.relationships if r["relation_type"] == "DEFINES"
    ]
    assert defines, "No DEFINES edges produced"
    for edge in defines:
        assert edge["from_canonical_id"] in repo_graph.entities
        assert edge["to_canonical_id"] in repo_graph.entities


# ---------------------------------------------------------------------
# WP-G3 acceptance criteria on a synthetic repo
# ---------------------------------------------------------------------

CALLS_SOURCE = (
    "def foo():\n"
    "    return 1\n"
    "\n"
    "\n"
    "def bar():\n"
    "    foo()\n"
    "    return foo()\n"
    "\n"
    "\n"
    "def baz():\n"
    "    return foo()\n"
)


@pytest.fixture()
def calls_graph(tmp_path):
    (tmp_path / "app.py").write_text(CALLS_SOURCE, encoding="utf-8")
    return RepoGraphBuilder(tmp_path, ingestion_id=str(uuid4())).build()


def _call_edges(graph):
    return [r for r in graph.relationships if r["relation_type"] == "CALL"]


def test_repeated_calls_aggregate_into_one_edge(calls_graph):
    """Calling foo() twice from bar() → one CALL edge, count 2, both linenos."""
    edges = [
        e for e in _call_edges(calls_graph)
        if e["from_canonical_id"] == "app.py#bar"
        and e["to_canonical_id"] == "app.py#foo"
    ]
    assert len(edges) == 1, f"Expected one aggregated edge, got {edges}"
    meta = edges[0]["relationship_metadata"]
    assert meta["count"] == 2
    assert meta["call_sites"] == [6, 7]


def test_distinct_callers_get_distinct_edges(calls_graph):
    """No last-write-wins: bar and baz each get their own edge to foo."""
    froms = {
        e["from_canonical_id"]
        for e in _call_edges(calls_graph)
        if e["to_canonical_id"] == "app.py#foo"
    }
    assert froms == {"app.py#bar", "app.py#baz"}


def test_no_call_rows_in_synthetic_graph(calls_graph):
    assert not any(
        a["artifact_type"] == "CALL" for a in calls_graph.all_entities()
    )


def test_rebuild_determinism(tmp_path):
    """Two consecutive builds produce identical entity and edge sets."""
    (tmp_path / "app.py").write_text(CALLS_SOURCE, encoding="utf-8")
    g1 = RepoGraphBuilder(tmp_path, ingestion_id="fixed-id").build()
    g2 = RepoGraphBuilder(tmp_path, ingestion_id="fixed-id").build()
    assert sorted(g1.entities.keys()) == sorted(g2.entities.keys())
    assert g1.relationships == g2.relationships
