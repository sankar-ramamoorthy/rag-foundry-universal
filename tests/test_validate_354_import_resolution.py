"""Unit tests for the pure helpers of scripts/validate_354_import_resolution.py."""

import sys
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

import validate_354_import_resolution as v  # noqa: E402


def test_project_root_of_uses_nearest_ancestor_only():
    roots = ("svc", "svc/plugins/p")
    assert v.project_root_of("svc/src/a.py", roots) == "svc"
    assert v.project_root_of("svc/plugins/p/src/a.py", roots) == "svc/plugins/p"
    assert v.project_root_of("scripts/tool.py", roots) is None


def test_last_name_handles_symbols_and_placeholders():
    assert v.last_name("svc/src/a.py#Cls.method") == "method"
    assert v.last_name("EXTERNAL_SYMBOL:src.core.config.get_settings") == "get_settings"


def test_reach_is_bfs_depth_over_selected_relations():
    out = defaultdict(list)
    out["a"] = [("b", "CALL"), ("x", "DEFINES")]
    out["b"] = [("c", "CALL")]
    assert v.reach(out, "a", {"CALL"}) == {"a": 0, "b": 1, "c": 2}
    assert v.reach(out, "a", {"CALL"}, depth=1) == {"a": 0, "b": 1}
