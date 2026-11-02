# ingestion_service/tests/codebase/test_env_package_not_ignored.py
"""
Issue #307: a directory merely *named* ``env`` is a legitimate package
(e.g. Hatch's ``src/hatch/cli/env/``) and must be ingested, while a real
virtualenv named ``env`` stays excluded.
"""
from pathlib import Path
from uuid import uuid4

import pytest

from src.core.codebase.repo_graph_builder import RepoGraphBuilder
from src.core.codebase.structural_inventory import walk_all_files

pytestmark = pytest.mark.unit

PY = "def {name}():\n    return 1\n"


def _write(root: Path, rel: str, name: str = "f") -> None:
    p = root / rel
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(PY.format(name=name), encoding="utf-8")


def _hatch_layout(root: Path) -> None:
    for mod, fn in (("show", "show"), ("lock", "lock"), ("run", "run")):
        _write(root, f"src/hatch/cli/env/{mod}.py", fn)
    _write(root, "src/hatch/cli/env/__init__.py", "init")
    _write(root, "src/hatch/cli/python/show.py", "pyshow")


def _build(root: Path):
    return RepoGraphBuilder(root, ingestion_id=str(uuid4())).build()


def test_nested_env_package_is_ingested(tmp_path):
    _hatch_layout(tmp_path)
    entities = set(_build(tmp_path).entities)
    for cid in (
        "src/hatch/cli/env/show.py#show",
        "src/hatch/cli/env/lock.py#lock",
        "src/hatch/cli/env/run.py#run",
    ):
        assert cid in entities


def test_top_level_env_package_without_markers_is_ingested(tmp_path):
    _write(tmp_path, "env/settings.py", "load")
    assert "env/settings.py#load" in set(_build(tmp_path).entities)


@pytest.mark.parametrize(
    "marker",
    [
        "env/pyvenv.cfg",
        "env/bin/activate",
        "env/Scripts/activate",
        "env/lib/python3.12/site-packages/.keep",
        "env/Lib/site-packages/.keep",
    ],
)
def test_real_virtualenv_named_env_is_excluded(tmp_path, marker):
    _write(tmp_path, "app/main.py", "main")
    marker_path = tmp_path / marker
    marker_path.parent.mkdir(parents=True, exist_ok=True)
    marker_path.write_text("", encoding="utf-8")
    _write(tmp_path, "env/lib/python3.12/site-packages/pkg/junk.py", "junk")

    entities = set(_build(tmp_path).entities)
    assert "app/main.py#main" in entities
    assert not [c for c in entities if c.startswith("env/")]


def test_nested_virtualenv_inside_package_is_excluded(tmp_path):
    _write(tmp_path, "svc/api.py", "api")
    (tmp_path / "svc/env").mkdir(parents=True)
    (tmp_path / "svc/env/pyvenv.cfg").write_text("", encoding="utf-8")
    _write(tmp_path, "svc/env/junk.py", "junk")
    entities = set(_build(tmp_path).entities)
    assert "svc/api.py#api" in entities
    assert "svc/env/junk.py#junk" not in entities


def test_inventory_walk_agrees_with_graph_walk(tmp_path):
    _hatch_layout(tmp_path)
    (tmp_path / "venvlike/env").mkdir(parents=True)
    (tmp_path / "venvlike/env/pyvenv.cfg").write_text("", encoding="utf-8")
    _write(tmp_path, "venvlike/env/junk.py", "junk")

    inventory = {
        p.relative_to(tmp_path).as_posix() for p in walk_all_files(tmp_path)
    }
    graph = {
        p.relative_to(tmp_path).as_posix()
        for p in RepoGraphBuilder(tmp_path, ingestion_id=str(uuid4()))._walk_repo()
    }
    assert "src/hatch/cli/env/show.py" in inventory
    assert not [p for p in inventory if p.startswith("venvlike/env/")]
    assert graph <= inventory
