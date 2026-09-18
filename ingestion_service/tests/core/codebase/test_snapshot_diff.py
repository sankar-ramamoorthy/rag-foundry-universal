# ingestion_service/tests/core/codebase/test_snapshot_diff.py
"""T013 (issue #196): unit tests for snapshot_diff.classify — no DB/Docker."""
import pytest

from src.core.codebase.snapshot_diff import classify

pytestmark = pytest.mark.unit


def test_empty_prior_classifies_everything_as_new():
    diff = classify({"pkg/a.py": "h1", "pkg/b.py": "h2"}, {})
    assert diff.new == {"pkg/a.py", "pkg/b.py"}
    assert diff.unchanged == frozenset()
    assert diff.changed == frozenset()
    assert diff.deleted == frozenset()


def test_matching_hash_classifies_unchanged():
    diff = classify({"pkg/a.py": "h1"}, {"pkg/a.py": "h1"})
    assert diff.unchanged == {"pkg/a.py"}
    assert diff.changed == frozenset()
    assert diff.new == frozenset()
    assert diff.deleted == frozenset()


def test_mismatched_hash_classifies_changed():
    diff = classify({"pkg/a.py": "h2"}, {"pkg/a.py": "h1"})
    assert diff.changed == {"pkg/a.py"}
    assert diff.unchanged == frozenset()


def test_canonical_id_absent_from_current_classifies_deleted():
    diff = classify({}, {"pkg/a.py": "h1"})
    assert diff.deleted == {"pkg/a.py"}
    assert diff.new == frozenset()
    assert diff.unchanged == frozenset()
    assert diff.changed == frozenset()


def test_whitespace_only_change_classifies_changed_not_unchanged():
    # No semantic hashing (spec Edge Cases): a byte-level hash of
    # whitespace-only content differs, so it must classify as "changed",
    # never silently treated as "unchanged".
    prior_hash = "sha256-of-original-bytes"
    new_hash = "sha256-of-whitespace-edited-bytes"
    assert prior_hash != new_hash  # sanity: these represent different bytes
    diff = classify({"pkg/a.py": new_hash}, {"pkg/a.py": prior_hash})
    assert diff.changed == {"pkg/a.py"}
    assert diff.unchanged == frozenset()


def test_mixed_classification_across_multiple_files():
    current = {
        "pkg/unchanged.py": "h1",
        "pkg/changed.py": "h2-new",
        "pkg/new.py": "h3",
    }
    prior = {
        "pkg/unchanged.py": "h1",
        "pkg/changed.py": "h2-old",
        "pkg/deleted.py": "h4",
    }
    diff = classify(current, prior)
    assert diff.unchanged == {"pkg/unchanged.py"}
    assert diff.changed == {"pkg/changed.py"}
    assert diff.new == {"pkg/new.py"}
    assert diff.deleted == {"pkg/deleted.py"}
