# rag_orchestrator/tests/test_graph_cache_generation.py
"""
Issue #168 (WP-R5): get_cached_graph must key on repo_id's current
*generation*, not repo_id alone -- a re-ingested repo keeps the same
repo_id but gets a new ingestion_id, and the previous implementation kept
whichever graph it loaded first forever. Also verifies the cache is
bounded (LRU-evicted) rather than growing without limit across repos.
"""
from unittest.mock import MagicMock

import pytest

from rag_orchestrator.src.retrieval import codebase_utils
from src.retrieval.codebase_queries import CodebaseGraph, Node

pytestmark = pytest.mark.unit


@pytest.fixture(autouse=True)
def _clear_cache():
    """The graph cache is process-global module state -- isolate tests."""
    with codebase_utils._repo_graphs_lock:
        codebase_utils._repo_graphs.clear()
    yield
    with codebase_utils._repo_graphs_lock:
        codebase_utils._repo_graphs.clear()


def _graph(tag: str) -> CodebaseGraph:
    graph = CodebaseGraph()
    graph.add_node(Node(tag, f"{tag}.py"))
    return graph


def test_cold_load_fetches_and_caches_the_graph(monkeypatch):
    generation = MagicMock(return_value=("gen-1", "ready"))
    load = MagicMock(return_value=_graph("a"))
    monkeypatch.setattr(codebase_utils, "get_repo_generation", generation)
    monkeypatch.setattr(codebase_utils, "load_graph_for_repo", load)

    graph = codebase_utils.get_cached_graph("repo-x")

    assert set(graph.nodes) == {"a"}
    load.assert_called_once_with("repo-x")


def test_warm_hit_on_same_generation_does_not_refetch(monkeypatch):
    generation = MagicMock(return_value=("gen-1", "ready"))
    load = MagicMock(return_value=_graph("a"))
    monkeypatch.setattr(codebase_utils, "get_repo_generation", generation)
    monkeypatch.setattr(codebase_utils, "load_graph_for_repo", load)

    codebase_utils.get_cached_graph("repo-x")
    codebase_utils.get_cached_graph("repo-x")

    load.assert_called_once()


def test_rebuild_to_a_new_generation_is_observed_by_a_warm_worker(monkeypatch):
    """The exact defect #168 exists to fix: a re-ingested repo under the
    same repo_id must not keep serving the pre-rebuild graph forever."""
    generation = MagicMock(side_effect=[("gen-1", "ready"), ("gen-2", "ready")])
    load = MagicMock(side_effect=[_graph("old"), _graph("new")])
    monkeypatch.setattr(codebase_utils, "get_repo_generation", generation)
    monkeypatch.setattr(codebase_utils, "load_graph_for_repo", load)

    first = codebase_utils.get_cached_graph("repo-x")
    second = codebase_utils.get_cached_graph("repo-x")

    assert set(first.nodes) == {"old"}
    assert set(second.nodes) == {"new"}
    assert load.call_count == 2
    # Only the current generation stays cached -- not both.
    assert len(codebase_utils._repo_graphs) == 1
    assert codebase_utils._repo_graphs["repo-x"][0] == "gen-2"


def test_delete_and_recreate_cannot_reuse_old_cached_content(monkeypatch):
    """Delete makes the repo unknown (no ingestion_requests row); a
    recreate under the same repo_id gets a fresh generation id. Neither
    step may serve the pre-delete cached graph."""
    generation = MagicMock(
        side_effect=[("gen-1", "ready"), (None, "unknown"), ("gen-2", "ready")],
    )
    load = MagicMock(side_effect=[_graph("old"), _graph("new")])
    monkeypatch.setattr(codebase_utils, "get_repo_generation", generation)
    monkeypatch.setattr(codebase_utils, "load_graph_for_repo", load)

    codebase_utils.get_cached_graph("repo-x")
    after_delete = codebase_utils.get_cached_graph("repo-x")
    after_recreate = codebase_utils.get_cached_graph("repo-x")

    assert set(after_delete.nodes) == set()
    assert set(after_recreate.nodes) == {"new"}
    load.assert_called_with("repo-x")
    assert load.call_count == 2


def test_force_reload_bypasses_cache_even_on_same_generation(monkeypatch):
    generation = MagicMock(return_value=("gen-1", "ready"))
    load = MagicMock(side_effect=[_graph("a"), _graph("a-reloaded")])
    monkeypatch.setattr(codebase_utils, "get_repo_generation", generation)
    monkeypatch.setattr(codebase_utils, "load_graph_for_repo", load)

    codebase_utils.get_cached_graph("repo-x")
    reloaded = codebase_utils.get_cached_graph("repo-x", force_reload=True)

    assert set(reloaded.nodes) == {"a-reloaded"}
    assert load.call_count == 2


@pytest.mark.parametrize("status", ["building", "failed", "unknown"])
def test_no_completed_generation_returns_empty_graph_without_fetching(
    monkeypatch, status,
):
    generation = MagicMock(return_value=(None, status))
    load = MagicMock(side_effect=AssertionError("must not fetch full graph"))
    monkeypatch.setattr(codebase_utils, "get_repo_generation", generation)
    monkeypatch.setattr(codebase_utils, "load_graph_for_repo", load)

    graph = codebase_utils.get_cached_graph("repo-x")

    assert graph.nodes == {}
    load.assert_not_called()
    assert "repo-x" not in codebase_utils._repo_graphs


def test_cache_is_bounded_across_repos(monkeypatch):
    monkeypatch.setattr(codebase_utils, "_CACHE_MAX_REPOS", 2)
    generation = MagicMock(side_effect=[
        ("gen-a", "ready"), ("gen-b", "ready"), ("gen-c", "ready"),
    ])
    load = MagicMock(side_effect=[_graph("a"), _graph("b"), _graph("c")])
    monkeypatch.setattr(codebase_utils, "get_repo_generation", generation)
    monkeypatch.setattr(codebase_utils, "load_graph_for_repo", load)

    codebase_utils.get_cached_graph("repo-a")
    codebase_utils.get_cached_graph("repo-b")
    codebase_utils.get_cached_graph("repo-c")

    assert len(codebase_utils._repo_graphs) == 2
    assert "repo-a" not in codebase_utils._repo_graphs, (
        "least-recently-used entry (repo-a) must be evicted once the "
        "bound is exceeded"
    )
    assert set(codebase_utils._repo_graphs) == {"repo-b", "repo-c"}


def test_recently_used_repo_survives_eviction(monkeypatch):
    """LRU, not FIFO: re-touching repo-a must protect it from eviction."""
    monkeypatch.setattr(codebase_utils, "_CACHE_MAX_REPOS", 2)
    generation = MagicMock(side_effect=[
        ("gen-a", "ready"), ("gen-b", "ready"),
        ("gen-a", "ready"),  # re-touch repo-a (same generation -> cache hit)
        ("gen-c", "ready"),
    ])
    load = MagicMock(side_effect=[_graph("a"), _graph("b"), _graph("c")])
    monkeypatch.setattr(codebase_utils, "get_repo_generation", generation)
    monkeypatch.setattr(codebase_utils, "load_graph_for_repo", load)

    codebase_utils.get_cached_graph("repo-a")
    codebase_utils.get_cached_graph("repo-b")
    codebase_utils.get_cached_graph("repo-a")
    codebase_utils.get_cached_graph("repo-c")

    assert set(codebase_utils._repo_graphs) == {"repo-a", "repo-c"}
