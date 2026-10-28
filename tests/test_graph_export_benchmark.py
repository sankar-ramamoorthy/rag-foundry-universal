"""Pure-function checks for the opt-in graph export benchmark (#273); no DB."""

import importlib.util
import json
from pathlib import Path

import pytest

SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "graph_export_benchmark.py"
SPEC = importlib.util.spec_from_file_location("graph_export_benchmark", SCRIPT)
assert SPEC is not None and SPEC.loader is not None
bench = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(bench)


@pytest.mark.parametrize("name", ["ingestion_test", "bench", "My_Test_DB"])
def test_disposable_database_names_are_accepted(name):
    assert bench.check_database_url(f"postgresql://u:p@h:5/{name}") == name


@pytest.mark.parametrize("name", ["ingestion_db", "postgres", "prod"])
def test_other_database_names_are_refused_unless_forced(name):
    url = f"postgresql://u:p@h:5/{name}"
    with pytest.raises(ValueError, match="test/bench"):
        bench.check_database_url(url)
    assert bench.check_database_url(url, force=True) == name


def test_database_url_without_a_name_is_refused():
    with pytest.raises(ValueError, match="no database name"):
        bench.check_database_url("postgresql://u:p@h:5")


def test_fixture_writes_only_the_synthetic_repo():
    statements = bench.fixture_statements(100, 2000, 3)
    deletes = [s for s in statements if s.startswith("DELETE")]
    assert deletes and all(
        bench.REPO_ID in s or bench.INGESTION_ID in s for s in deletes)
    assert any("generate_series(1, 100)" in s for s in statements)
    assert any("generate_series(1, 3) k" in s for s in statements)


@pytest.mark.parametrize("args", [(0, 2000, 3), (10, 10, 3), (10, 2000, -1)])
def test_fixture_rejects_nonsensical_sizes(args):
    with pytest.raises(ValueError):
        bench.fixture_statements(*args)


def _body(nodes, edges):
    return json.dumps({"nodes": nodes, "relationships": edges}).encode()


def test_canonical_hash_ignores_ordering_but_not_content():
    a = {"canonical_id": "a"}
    b = {"canonical_id": "b"}
    e1 = {"to_canonical_id": "b", "relation_type": "CALLS"}
    e2 = {"to_canonical_id": "a", "relation_type": "DEFINES"}
    one = bench.canonical_hash(_body([a, b], {"a": [e1, e2]}))
    two = bench.canonical_hash(_body([b, a], {"a": [e2, e1]}))
    other = bench.canonical_hash(_body([a], {"a": [e1, e2]}))
    assert one == two
    assert one != other


def test_summarize_and_memory_projection():
    assert bench.summarize([1.0, 3.0, 2.0]) == {"min": 1.0, "median": 2.0, "max": 3.0}
    assert bench.projected_peak_mb(150, 400, 4, 1.25) == 150 + 4 * 400 * 1.25
