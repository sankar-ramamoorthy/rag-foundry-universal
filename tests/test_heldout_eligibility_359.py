"""Unit test for the reach helper of scripts/heldout_eligibility_359.py."""

import sys
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

import heldout_eligibility_359 as h  # noqa: E402


def test_reach_counts_distinct_functions_within_depth():
    out = defaultdict(list)
    out["h"] = ["a", "b"]
    out["a"] = ["c", "b"]
    out["c"] = ["d"]
    assert h.reach(out, "h") == 4
    assert h.reach(out, "h", depth=1) == 2
