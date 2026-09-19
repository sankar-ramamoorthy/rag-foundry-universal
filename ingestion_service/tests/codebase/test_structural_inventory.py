# ingestion_service/tests/codebase/test_structural_inventory.py
"""
Issue #197 (ORIENT): deterministic structural inventory.

structural_inventory.py's functions are pure (no DB/session/HTTP) -- these
tests exercise the walk/classify/find pipeline directly against small fixture
trees, including a trimmed copy of this repo's own docker-compose.yml
(dogfooding, per the #197 plan's verification approach).
"""

from pathlib import Path
from uuid import uuid4

import pytest

from src.core.codebase.repo_graph_builder import DEFAULT_IGNORED_DIRS, RepoGraphBuilder
from src.core.codebase.structural_inventory import (
    build_structural_inventory,
    classify_languages,
    find_compose_services,
    find_heuristic_dirs,
    find_manifests,
    inventory_to_graph_dicts,
    walk_all_files,
)

pytestmark = pytest.mark.unit

PY_SOURCE = "def greet():\n    return 'hello'\n"

TRIMMED_COMPOSE = """\
services:
  postgres:
    image: postgres:16
    container_name: ingestion-db

  ingestion_service:
    build:
      context: .
      dockerfile: ingestion_service/Dockerfile
    container_name: ingestion-service
    command: uvicorn src.api.v1.main:app --host 0.0.0.0 --port 8000

  gradio:
    build:
      context: .
      dockerfile: gradio/Dockerfile
    container_name: gradio-ui
"""


def _make_repo(root: Path) -> None:
    (root / "ingestion_service" / "src").mkdir(parents=True)
    (root / "ingestion_service" / "src" / "main.py").write_text(
        PY_SOURCE,
        encoding="utf-8",
    )
    (root / "ingestion_service" / "Dockerfile").write_text(
        "FROM python:3.12\n",
        encoding="utf-8",
    )
    (root / "ingestion_service" / "pyproject.toml").write_text(
        '[project]\nname = "x"\n',
        encoding="utf-8",
    )
    (root / "gradio").mkdir()
    (root / "gradio" / "Dockerfile").write_text("FROM python:3.12\n", encoding="utf-8")
    (root / "pyproject.toml").write_text('[project]\nname = "root"\n', encoding="utf-8")
    (root / "docker-compose.yml").write_text(TRIMMED_COMPOSE, encoding="utf-8")
    (root / "tests").mkdir()
    (root / "tests" / "test_main.py").write_text(PY_SOURCE, encoding="utf-8")
    (root / "docs").mkdir()
    (root / "docs" / "readme.md").write_text("# Docs\n", encoding="utf-8")

    for junk_dir in sorted(DEFAULT_IGNORED_DIRS):
        d = root / junk_dir
        d.mkdir()
        (d / "junk.py").write_text(PY_SOURCE, encoding="utf-8")

    hidden = root / ".hidden"
    hidden.mkdir()
    (hidden / "secret.py").write_text(PY_SOURCE, encoding="utf-8")


def test_walk_all_files_sees_unsupported_files_and_prunes_ignored(tmp_path):
    _make_repo(tmp_path)
    walked = sorted(
        p.relative_to(tmp_path).as_posix() for p in walk_all_files(tmp_path)
    )

    # Dockerfiles/compose/manifests are invisible to EXTRACTORS-filtered
    # _walk_repo, but must appear here.
    assert "docker-compose.yml" in walked
    assert "ingestion_service/Dockerfile" in walked
    assert "ingestion_service/pyproject.toml" in walked
    assert "pyproject.toml" in walked

    # Ignore-dir/dotfile pruning still applies, same convention as
    # _walk_repo/_discover_crate_roots.
    assert not any(
        w.startswith(tuple(f"{d}/" for d in DEFAULT_IGNORED_DIRS)) for w in walked
    )
    assert not any(w.startswith(".hidden") for w in walked)


def test_walk_all_files_deterministic_repeat_calls(tmp_path):
    # Same convention as _walk_repo: sorted per-directory (dirnames and
    # filenames), not a global lexicographic sort of full relative paths --
    # the invariant that matters is that repeat calls agree exactly.
    _make_repo(tmp_path)
    first = [p.relative_to(tmp_path).as_posix() for p in walk_all_files(tmp_path)]
    second = [p.relative_to(tmp_path).as_posix() for p in walk_all_files(tmp_path)]
    assert first == second


def test_classify_languages_counts(tmp_path):
    _make_repo(tmp_path)
    files = walk_all_files(tmp_path)
    counts = classify_languages(files, tmp_path)
    assert counts["python"] >= 2  # main.py + tests/test_main.py
    assert counts["yaml"] >= 1  # docker-compose.yml
    assert counts["toml"] >= 2  # two pyproject.toml
    assert counts["markdown"] >= 1  # docs/readme.md


def test_find_manifests_exact_basename_only(tmp_path):
    _make_repo(tmp_path)
    (tmp_path / "requirements-dev.txt").write_text("pytest\n", encoding="utf-8")
    files = walk_all_files(tmp_path)
    manifests = find_manifests(files, tmp_path)
    paths = {m.path for m in manifests}

    assert "pyproject.toml" in paths
    assert "ingestion_service/pyproject.toml" in paths
    # near-miss basename must NOT be treated as a manifest hit
    assert "requirements-dev.txt" not in paths


def test_find_compose_services_extracts_expected_facts(tmp_path):
    _make_repo(tmp_path)
    files = walk_all_files(tmp_path)
    services, gaps = find_compose_services(files, tmp_path)
    by_name = {s.name: s for s in services}

    assert set(by_name) == {"postgres", "ingestion_service", "gradio"}
    assert by_name["ingestion_service"].dockerfile == "ingestion_service/Dockerfile"
    assert by_name["ingestion_service"].container_name == "ingestion-service"
    assert by_name["ingestion_service"].entry_point is not None
    assert by_name["ingestion_service"].entry_point_source == "compose.command"

    # postgres has no `command:` -> entry point genuinely unknown, not omitted
    assert by_name["postgres"].entry_point is None
    assert any(
        g.category == "entry_point" and "postgres" in (g.path or "") for g in gaps
    )


def test_find_compose_services_unparseable_yaml_produces_gap_not_crash(tmp_path):
    (tmp_path / "docker-compose.yml").write_text(
        "services: [this is not: a map", encoding="utf-8"
    )
    files = walk_all_files(tmp_path)
    services, gaps = find_compose_services(files, tmp_path)

    assert services == []
    assert any(g.category == "compose_parse" for g in gaps)


def test_find_heuristic_dirs(tmp_path):
    _make_repo(tmp_path)
    files = walk_all_files(tmp_path)
    dirs = find_heuristic_dirs(files, tmp_path)

    assert "tests" in dirs["test_dirs"]
    assert "docs" in dirs["docs_dirs"]


def test_build_structural_inventory_is_deterministic(tmp_path):
    _make_repo(tmp_path)
    first = build_structural_inventory(tmp_path)
    second = build_structural_inventory(tmp_path)
    assert first == second


def test_build_structural_inventory_summary_dict_has_no_silent_omissions(tmp_path):
    _make_repo(tmp_path)
    inventory = build_structural_inventory(tmp_path)
    summary = inventory.summary_dict()

    assert summary["file_counts"]["total"] == (
        summary["file_counts"]["indexed"] + summary["file_counts"]["non_indexed"]
    )
    assert "gaps" in summary
    assert isinstance(summary["gaps"], list)
    assert summary["heuristic_fields"] == ["test_dirs", "docs_dirs"]

    manifest_paths = {m["path"] for m in summary["manifests"]}
    assert "pyproject.toml" in manifest_paths
    service_names = {s["name"] for s in summary["services"]}
    assert service_names == {"postgres", "ingestion_service", "gradio"}
    ingestion_service_entry = next(
        s for s in summary["services"] if s["name"] == "ingestion_service"
    )
    assert ingestion_service_entry["dockerfile"] == "ingestion_service/Dockerfile"
    assert ingestion_service_entry["container_name"] == "ingestion-service"


def test_inventory_to_graph_dicts_no_canonical_id_collision_with_symbol_graph(tmp_path):
    """The hard constraint from the #197 plan: an inventory node must never
    be emitted for a relative_path already indexed by the symbol graph."""
    _make_repo(tmp_path)
    builder = RepoGraphBuilder(tmp_path, ingestion_id=str(uuid4()))
    graph = builder.build()
    indexed_paths = set(graph.files.keys())

    inventory = build_structural_inventory(tmp_path, indexed_paths=indexed_paths)
    nodes, _relationships = inventory_to_graph_dicts(
        str(uuid4()),
        inventory,
        indexed_paths,
        tmp_path,
    )

    file_node_canonical_ids = {
        n["canonical_id"] for n in nodes if n["doc_type"] in ("file", "manifest")
    }
    assert file_node_canonical_ids.isdisjoint(indexed_paths)
    # Dockerfiles/compose/manifests, which _walk_repo never sees, must show up.
    assert "docker-compose.yml" in file_node_canonical_ids
    assert "ingestion_service/Dockerfile" in file_node_canonical_ids
    assert "pyproject.toml" in file_node_canonical_ids


def test_inventory_to_graph_dicts_manifest_doc_type(tmp_path):
    _make_repo(tmp_path)
    indexed_paths: set[str] = set()
    inventory = build_structural_inventory(tmp_path, indexed_paths=indexed_paths)
    nodes, _relationships = inventory_to_graph_dicts(
        str(uuid4()),
        inventory,
        indexed_paths,
        tmp_path,
    )
    manifest_nodes = {
        n["canonical_id"]: n for n in nodes if n["doc_type"] == "manifest"
    }
    assert "pyproject.toml" in manifest_nodes
    assert manifest_nodes["pyproject.toml"]["text"] == ""


def test_inventory_to_graph_dicts_service_canonical_id_is_namespaced(tmp_path):
    _make_repo(tmp_path)
    indexed_paths: set[str] = set()
    inventory = build_structural_inventory(tmp_path, indexed_paths=indexed_paths)
    nodes, relationships = inventory_to_graph_dicts(
        str(uuid4()),
        inventory,
        indexed_paths,
        tmp_path,
    )
    service_nodes = [n for n in nodes if n["doc_type"] == "service"]
    assert service_nodes
    for node in service_nodes:
        assert node["canonical_id"].startswith("compose:docker-compose.yml#")
        # Never a bare relative path -- can't collide with a file identity.
        assert node["canonical_id"] != node["relative_path"]

    declares = [r for r in relationships if r["relation_type"] == "DECLARES"]
    assert any(
        r["from_canonical_id"] == "compose:docker-compose.yml#ingestion_service"
        and r["to_canonical_id"] == "ingestion_service/Dockerfile"
        for r in declares
    )
