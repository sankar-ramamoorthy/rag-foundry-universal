"""Unit tests for the pure parts of scripts/fulltext_diagnostic_342.py (#342)."""

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

import fulltext_diagnostic_342 as f  # noqa: E402

ROWS = [
    ("svc/src/a.py#x", 0, "python source", 0.5),
    ("svc/tests/test_a.py#t", 0, "python source", 0.9),
    ("DOCS/n.md#s", 0, "markdown_section", 0.8),
    ("svc/src/a.py#x", 1, "python source", 0.7),
    ("svc/src/b.py#y", 0, "python source", 0.0),
]


def test_scopes_filter_docs_then_test_paths():
    assert [r[0] for r in f.ranked(ROWS, "all", positive_only=True)] == [
        "svc/tests/test_a.py#t",
        "DOCS/n.md#s",
        "svc/src/a.py#x",
        "svc/src/a.py#x",
    ]
    assert {r[0] for r in f.ranked(ROWS, "source", True)} == {
        "svc/tests/test_a.py#t",
        "svc/src/a.py#x",
    }
    assert {r[0] for r in f.ranked(ROWS, "path_role", True)} == {"svc/src/a.py#x"}


def test_zero_scores_are_dropped_only_for_fulltext():
    assert len(f.ranked(ROWS, "all", positive_only=False)) == 5
    assert len(f.ranked(ROWS, "all", positive_only=True)) == 4


def test_artifact_rank_is_best_chunk_and_fusion_is_rrf():
    chunks = f.ranked(ROWS, "all", True)
    assert f.artifact_ranks(chunks) == {
        "svc/tests/test_a.py#t": 1,
        "DOCS/n.md#s": 2,
        "svc/src/a.py#x": 3,
    }
    fused = dict(f.fuse([chunks, list(reversed(chunks))]))
    assert fused["svc/src/a.py#x"] == 1 / (f.RRF_K + 3) + 1 / (f.RRF_K + 1)


def test_recall_counts_targets_within_cutoff():
    n = len(f.CODE_TARGETS)
    ranks = dict.fromkeys(f.CODE_TARGETS)
    first, second = list(f.CODE_TARGETS)[:2]
    ranks[first], ranks[second] = 5, 60
    assert f.recall(ranks) == {
        "@20": round(1 / n, 3),
        "@50": round(1 / n, 3),
        "@100": round(2 / n, 3),
    }


def test_code_targets_exclude_textless_routes():
    assert all(not v.startswith("route:") for v in f.CODE_TARGETS.values())
    assert len(f.CODE_TARGETS) == 11
