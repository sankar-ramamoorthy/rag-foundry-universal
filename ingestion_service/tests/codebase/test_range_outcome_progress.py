# ingestion_service/tests/codebase/test_range_outcome_progress.py
"""
Issue #416: successful artifact reuse must not imply successful range patching.

Ingestion progress (the `embed_progress` that the status endpoint returns and
that persists as the final result) states, for every incremental run that reused
artifacts, what happened to their source ranges: patched, partly patched,
retried without ranges, not supported by the vector store, or not reported.
"""
from types import SimpleNamespace

import pytest

from src.api.v1.codebase_ingest import _report_range_outcome

pytestmark = pytest.mark.unit


def stats(patched=0, skipped_total=0, unsupported=False, retried=0, requested=0):
    return {
        "requested": requested,
        "patched": patched,
        "skipped_total": skipped_total,
        "skipped": [
            {"document_id": "d", "chunk_index": 0, "reason": "digest mismatch"}
        ]
        * min(skipped_total, 3),
        "unsupported": unsupported,
        "retried_without_ranges": retried,
    }


def report(last, reused=3, requested=10):
    store = SimpleNamespace(last_range_patch=last)
    progress: dict = {}
    pipeline = SimpleNamespace(_vector_store=store)
    _report_range_outcome(pipeline, progress, reused, requested)
    return progress


def test_full_success_is_patched_and_says_how_many():
    p = report(stats(patched=10, requested=10))
    assert p["ranges_outcome"] == "patched"
    counts = (p["ranges_requested"], p["ranges_patched"], p["ranges_skipped"])
    assert counts == (10, 10, 0)
    assert p["ranges_retried_batches"] == 0 and p["ranges_unsupported"] is False


def test_skipped_passages_make_it_partial_not_patched():
    p = report(stats(patched=7, skipped_total=3, requested=10))
    assert p["ranges_outcome"] == "partial"
    assert (p["ranges_patched"], p["ranges_skipped"]) == (7, 3)


def test_a_retry_without_ranges_is_visible_even_though_reuse_succeeded():
    p = report(stats(patched=4, retried=2, requested=10))
    assert p["ranges_outcome"] == "retried_without_ranges"
    assert p["ranges_retried_batches"] == 2
    assert p["ranges_patched"] == 4 < p["ranges_requested"]


def test_an_older_vector_store_is_visible():
    p = report(stats(unsupported=True, requested=10))
    assert p["ranges_outcome"] == "unsupported" and p["ranges_unsupported"] is True
    assert p["ranges_patched"] == 0


def test_unsupported_outranks_retry_and_partial():
    p = report(stats(unsupported=True, retried=1, skipped_total=2, requested=10))
    assert p["ranges_outcome"] == "unsupported"


def test_reused_artifacts_with_no_reported_outcome_say_so():
    p = report(None, reused=3, requested=10)
    assert p["ranges_outcome"] == "not_reported"
    assert p["ranges_requested"] == 10 and p["ranges_patched"] == 0


def test_a_run_that_reused_nothing_adds_no_range_keys():
    assert report(None, reused=0, requested=0) == {}
    assert report(stats(patched=0), reused=0, requested=0) == {}


def test_reused_artifacts_that_had_nothing_to_patch_is_not_applicable():
    p = report(None, reused=2, requested=0)
    assert p["ranges_outcome"] == "not_applicable"


def test_a_mock_store_cannot_inject_a_fake_outcome():
    store = SimpleNamespace(last_range_patch="not a dict")
    progress: dict = {}
    _report_range_outcome(SimpleNamespace(_vector_store=store), progress, 2, 5)
    assert progress["ranges_outcome"] == "not_reported"


def test_the_warning_names_skipped_passages(caplog):
    with caplog.at_level("WARNING"):
        report(stats(patched=1, skipped_total=2, requested=3))
    assert any(
        "kept their previous range metadata" in r.message for r in caplog.records
    )


def test_a_retry_is_logged_as_a_warning(caplog):
    with caplog.at_level("WARNING"):
        report(stats(retried=1, requested=3))
    assert any(
        "range patching was not completed" in r.message and "retried" in r.message
        for r in caplog.records
    )
