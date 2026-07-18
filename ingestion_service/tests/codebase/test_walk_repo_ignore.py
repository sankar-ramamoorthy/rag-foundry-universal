# ingestion_service/tests/codebase/test_walk_repo_ignore.py
"""
F-16: default repository ignore semantics.

Ignored directories (node_modules, venv, build, dist, target, vendor,
__pycache__, dot-dirs, ...) must produce no artifacts when a repo is
ingested. Graph semantics for non-ignored files are unchanged.
"""
import pytest
from pathlib import Path
from uuid import uuid4

from src.core.codebase.repo_graph_builder import (
    RepoGraphBuilder,
    DEFAULT_IGNORED_DIRS,
)

pytestmark = pytest.mark.unit

PY_SOURCE = "def greet():\n    return 'hello'\n"
MD_SOURCE = "# Title\n\nSome docs.\n"


def _make_repo(root: Path) -> None:
    """Small fake repo: two real files plus junk in every ignored dir."""
    (root / "app").mkdir()
    (root / "app" / "main.py").write_text(PY_SOURCE, encoding="utf-8")
    (root / "README.md").write_text(MD_SOURCE, encoding="utf-8")

    for junk_dir in sorted(DEFAULT_IGNORED_DIRS):
        d = root / junk_dir / "pkg"
        d.mkdir(parents=True)
        (d / "junk.py").write_text(PY_SOURCE, encoding="utf-8")
        (d / "junk.md").write_text(MD_SOURCE, encoding="utf-8")

    # dot-directories are ignored by a separate rule
    hidden = root / ".hidden"
    hidden.mkdir()
    (hidden / "secret.py").write_text(PY_SOURCE, encoding="utf-8")

    # nested ignored dir inside a legitimate dir
    nested = root / "app" / "node_modules" / "lib"
    nested.mkdir(parents=True)
    (nested / "vendored.py").write_text(PY_SOURCE, encoding="utf-8")


@pytest.fixture()
def repo_graph(tmp_path):
    _make_repo(tmp_path)
    builder = RepoGraphBuilder(tmp_path, ingestion_id=str(uuid4()))
    return builder.build()


def test_ignored_dirs_produce_no_artifacts(repo_graph):
    ignored_prefixes = tuple(
        f"{d}/" for d in DEFAULT_IGNORED_DIRS
    ) + (".hidden/", "app/node_modules/")

    offenders = [
        cid for cid in repo_graph.entities
        if cid.startswith(ignored_prefixes)
    ]
    assert offenders == [], (
        f"Artifacts were created from ignored directories: {offenders}"
    )


def test_ignored_dirs_produce_no_relationships(repo_graph):
    ignored_prefixes = tuple(
        f"{d}/" for d in DEFAULT_IGNORED_DIRS
    ) + (".hidden/", "app/node_modules/")

    offenders = [
        rel for rel in repo_graph.relationships
        if rel["from_canonical_id"].startswith(ignored_prefixes)
        or rel["to_canonical_id"].startswith(ignored_prefixes)
    ]
    assert offenders == [], (
        f"Relationships touch ignored directories: {offenders}"
    )


def test_non_ignored_files_still_ingested(repo_graph):
    canonical_ids = set(repo_graph.entities)

    assert "app/main.py" in canonical_ids, "MODULE artifact missing"
    assert "app/main.py#greet" in canonical_ids, "FUNCTION artifact missing"
    assert any(
        cid.startswith("README.md") for cid in canonical_ids
    ), "Markdown artifacts missing"


def test_only_expected_files_walked(tmp_path):
    _make_repo(tmp_path)
    builder = RepoGraphBuilder(tmp_path, ingestion_id=str(uuid4()))

    walked = sorted(
        p.relative_to(tmp_path).as_posix() for p in builder._walk_repo()
    )
    assert walked == ["README.md", "app/main.py"]
