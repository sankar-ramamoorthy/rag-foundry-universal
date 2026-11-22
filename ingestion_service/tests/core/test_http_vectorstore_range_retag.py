# ingestion_service/tests/core/test_http_vectorstore_range_retag.py
"""
Issue #416, WP4: the vector-store client carries source-range patches on the
retag request and survives a failing or older vector store without losing reuse.

requests.post is replaced; nothing here touches a network or database. The
vector store's own guarantees (digest, generation fence, atomicity) are tested
in vector_store_service; this file checks what the client sends and what it does
with the answers.
"""
from unittest.mock import MagicMock

import pytest
import requests

from src.core.http_vectorstore import HttpVectorStore

pytestmark = pytest.mark.unit

SHA = "a" * 64


def entry(index, start=1, end=2):
    return {"chunk_index": index, "text_sha256": SHA, "start_line": start,
            "end_line": end, "range_reason": None}


def response(body, status=200):
    resp = MagicMock()
    resp.status_code = status
    resp.json.return_value = body
    if status >= 400:
        resp.raise_for_status.side_effect = requests.HTTPError(f"{status}")
    else:
        resp.raise_for_status.return_value = None
    return resp


class Server:
    """A fake retag endpoint that records every request body."""

    def __init__(self, patched=True, fail_with_ranges=False, fail_always=False):
        self.sent = []
        self.patched = patched
        self.fail_with_ranges = fail_with_ranges
        self.fail_always = fail_always

    def __call__(self, url, json=None, timeout=None):
        assert url.endswith("/v1/vectors/retag")
        self.sent.append(json)
        has_ranges = bool(json.get("source_ranges_by_document_id"))
        if self.fail_always or (self.fail_with_ranges and has_ranges):
            return response({}, 422)
        body = {"status": "ok", "count": 2 * len(json["document_ids"]),
                "document_ids": json["document_ids"]}
        if self.patched:
            n = sum(len(v) for v in (json.get("source_ranges_by_document_id")
                                     or {}).values())
            body.update(ranges_patched=n, ranges_skipped=[], ranges_skipped_total=0)
        return response(body)


@pytest.fixture
def store(monkeypatch):
    return HttpVectorStore("http://vector.test")


def retag(store, server, monkeypatch, docs, ranges, **kw):
    monkeypatch.setattr(requests, "post", server)
    return store.retag_ingestion_id(
        docs, "new", None, expected_ingestion_id="old",
        source_ranges_by_document_id=ranges, **kw,
    )


def test_ranges_ride_the_retag_request_for_their_own_documents(store, monkeypatch):
    server = Server()
    rows, docs = retag(
        store, server, monkeypatch, ["d1", "d2"],
        {"d1": [entry(0), entry(1)], "d2": [entry(0)]},
    )
    assert len(server.sent) == 1
    body = server.sent[0]
    assert body["expected_ingestion_id"] == "old" and body["new_ingestion_id"] == "new"
    assert set(body["source_ranges_by_document_id"]) == {"d1", "d2"}
    assert rows == 4 and docs == {"d1", "d2"}
    assert store.last_range_patch["patched"] == 3
    assert store.last_range_patch["skipped_total"] == 0


def test_without_ranges_the_request_is_exactly_the_old_one(store, monkeypatch):
    server = Server()
    retag(store, server, monkeypatch, ["d1"], None)
    assert "source_ranges_by_document_id" not in server.sent[0]
    assert store.last_range_patch is None


def test_a_batch_carries_only_its_own_documents_ranges(store, monkeypatch):
    store.RETAG_BATCH_SIZE = 2
    server = Server()
    docs = ["d1", "d2", "d3"]
    retag(store, server, monkeypatch, docs, {d: [entry(0)] for d in docs})
    assert [b["document_ids"] for b in server.sent] == [["d1", "d2"], ["d3"]]
    assert [set(b["source_ranges_by_document_id"]) for b in server.sent] == [
        {"d1", "d2"}, {"d3"}]


def test_a_request_is_split_by_patch_count_but_never_inside_a_document(
    store, monkeypatch
):
    store.RANGE_PATCHES_PER_REQUEST = 4
    server = Server()
    ranges = {"d1": [entry(i) for i in range(3)],
              "d2": [entry(i) for i in range(3)],
              "d3": [entry(i) for i in range(9)]}  # more than one request alone
    retag(store, server, monkeypatch, ["d1", "d2", "d3"], ranges)
    assert [b["document_ids"] for b in server.sent] == [["d1"], ["d2"], ["d3"]]
    for body in server.sent:
        assert set(body["source_ranges_by_document_id"]) == set(body["document_ids"])


def test_skips_are_aggregated_and_bounded(store, monkeypatch):
    store.RETAG_BATCH_SIZE = 1

    def post(url, json=None, timeout=None):
        skipped = [{"document_id": json["document_ids"][0], "chunk_index": 0,
                    "reason": "digest mismatch"}]
        return response({"status": "ok", "count": 1,
                         "document_ids": json["document_ids"],
                         "ranges_patched": 1, "ranges_skipped": skipped,
                         "ranges_skipped_total": 1})

    monkeypatch.setattr(requests, "post", post)
    store.retag_ingestion_id(
        ["d1", "d2"], "new", None, expected_ingestion_id="old",
        source_ranges_by_document_id={"d1": [entry(0)], "d2": [entry(0)]},
    )
    stats = store.last_range_patch
    assert stats["patched"] == 2 and stats["skipped_total"] == 2
    assert {s["document_id"] for s in stats["skipped"]} == {"d1", "d2"}


def test_an_older_vector_store_is_noted_not_failed(store, monkeypatch):
    server = Server(patched=False)  # response has no ranges_patched
    rows, docs = retag(store, server, monkeypatch, ["d1"], {"d1": [entry(0)]})
    assert docs == {"d1"}
    assert store.last_range_patch["unsupported"] is True
    assert store.last_range_patch["patched"] == 0


def test_a_rejected_range_patch_retries_that_batch_without_ranges(store, monkeypatch):
    """The vector store rolled the whole request back, so a clean retry without
    ranges still reuses the artifact (it keeps its legacy range reason)."""
    server = Server(fail_with_ranges=True)
    rows, docs = retag(store, server, monkeypatch, ["d1"], {"d1": [entry(0)]})
    assert docs == {"d1"}
    assert len(server.sent) == 2
    assert server.sent[0].get("source_ranges_by_document_id")
    assert "source_ranges_by_document_id" not in server.sent[1]
    assert store.last_range_patch["retried_without_ranges"] == 1
    assert store.last_range_patch["patched"] == 0


def test_a_failing_plain_retag_still_fails_loudly(store, monkeypatch):
    server = Server(fail_always=True)
    with pytest.raises(requests.HTTPError):
        retag(store, server, monkeypatch, ["d1"], {"d1": [entry(0)]})
    assert len(server.sent) == 2  # tried with ranges, then without; both failed


def test_a_failing_request_without_ranges_is_not_retried(store, monkeypatch):
    server = Server(fail_always=True)
    with pytest.raises(requests.HTTPError):
        retag(store, server, monkeypatch, ["d1"], None)
    assert len(server.sent) == 1


# --- timeouts: the outcome is unknown, so nothing is retried or re-embedded ---

from src.core.http_vectorstore import RetagIncompleteError  # noqa: E402


class TimingOut(Server):
    def __init__(self, fail_on_call):
        super().__init__()
        self.fail_on_call = fail_on_call

    def __call__(self, url, json=None, timeout=None):
        if len(self.sent) + 1 == self.fail_on_call:
            self.sent.append(json)
            raise requests.Timeout("read timed out")
        return super().__call__(url, json=json, timeout=timeout)


def test_a_timeout_is_never_retried_and_fails_loudly(store, monkeypatch):
    server = TimingOut(fail_on_call=1)
    with pytest.raises(RetagIncompleteError) as caught:
        retag(store, server, monkeypatch, ["d1"], {"d1": [entry(0)]})
    assert len(server.sent) == 1  # no retry with or without ranges
    assert caught.value.documents_moved == 0 and caught.value.documents_total == 1


def test_a_timeout_part_way_reports_how_many_documents_had_already_moved(
    store, monkeypatch
):
    store.RETAG_BATCH_SIZE = 1
    server = TimingOut(fail_on_call=3)
    docs = ["d1", "d2", "d3", "d4"]
    with pytest.raises(RetagIncompleteError) as caught:
        retag(store, server, monkeypatch, docs, {d: [entry(0)] for d in docs})
    assert (caught.value.documents_moved, caught.value.documents_total) == (2, 4)
    assert "not retried" in str(caught.value)
    assert len(server.sent) == 3  # d4 was never attempted


def test_a_lost_connection_without_ranges_is_the_same_failure(store, monkeypatch):
    def post(url, json=None, timeout=None):
        raise requests.ConnectionError("reset")

    monkeypatch.setattr(requests, "post", post)
    with pytest.raises(RetagIncompleteError):
        store.retag_ingestion_id(["d1"], "new", None, expected_ingestion_id="old")


def test_requests_are_small_and_the_timeout_is_generous(store):
    assert store.RANGE_PATCHES_PER_REQUEST <= 500
    assert store.RETAG_TIMEOUT_SECONDS >= 120


def test_the_configured_timeout_is_what_is_sent(store, monkeypatch):
    seen = []

    def post(url, json=None, timeout=None):
        seen.append(timeout)
        return response(
            {"status": "ok", "count": 1, "document_ids": json["document_ids"]}
        )

    monkeypatch.setattr(requests, "post", post)
    store.retag_ingestion_id(["d1"], "new", None, expected_ingestion_id="old")
    assert seen == [store.RETAG_TIMEOUT_SECONDS]
