"""Issue #416 WP3 (specs/015-per-window-source-ranges): the digest-guarded,
generation-fenced, atomic source-range patch carried by the retag request.

Unit level: psycopg is mocked, so these check what the store sends, what it
refuses before sending anything, and what it reports. The behavior that needs a
real database (the stored rows after success, rejection and failure injection)
is in test_range_patch.py.
"""
from unittest.mock import MagicMock, patch

import pytest
from pydantic import ValidationError

from src.api.v1.vectors import VectorRetagRequest, retag_vectors
from src.core.vectorstore.pgvector_store import PgVectorStore

pytestmark = pytest.mark.unit

DOC = "11111111-1111-1111-1111-111111111111"
DOC2 = "22222222-2222-2222-2222-222222222222"
SHA = "a" * 64


def ok(index=0, start=3, end=9, sha=SHA):
    return {"chunk_index": index, "text_sha256": sha, "start_line": start,
            "end_line": end, "range_reason": None}


def null(index=0, reason="artifact range not verified", sha=SHA):
    return {"chunk_index": index, "text_sha256": sha, "start_line": None,
            "end_line": None, "range_reason": reason}


def _cursor(mock_connect):
    conn = MagicMock()
    conn.__enter__.return_value = conn
    cursor = MagicMock()
    cursor.__enter__.return_value = cursor
    conn.cursor.return_value = cursor
    mock_connect.return_value = conn
    return cursor


# --- request validation (nothing reaches the store if the shape is wrong) ---


def request(**ranges):
    return VectorRetagRequest(
        document_ids=[DOC],
        new_ingestion_id="new",
        expected_ingestion_id="old",
        source_ranges_by_document_id=ranges or None,
    )


def test_request_accepts_ranges_and_reasons_and_stays_optional():
    assert VectorRetagRequest(
        document_ids=[DOC], new_ingestion_id="n", expected_ingestion_id="o"
    ).source_ranges_by_document_id is None
    parsed = request(**{DOC: [ok(0), null(1)]})
    assert [p.chunk_index for p in parsed.source_ranges_by_document_id[DOC]] == [0, 1]


@pytest.mark.parametrize(
    "bad",
    [
        {**ok(), "text_sha256": "xyz"},
        {**ok(), "text_sha256": "A" * 64},  # lowercase hex only
        {**ok(), "chunk_index": -1},
        {**ok(), "start_line": 0},
        {**ok(), "start_line": 9, "end_line": 3},
        {**ok(), "end_line": None},  # half a range
        {**ok(), "range_reason": "both"},  # a range with a reason
        null(reason=""),  # no range and no reason
        {**null(), "start_line": 3},  # a reason with half a range
        {"chunk_index": 0, "text_sha256": SHA, "start_line": 1, "end_line": 2,
         "range_reason": None, "vector": [1.0]},  # extra field: not location
    ],
)
def test_malformed_patch_entries_are_rejected_by_the_request_model(bad):
    with pytest.raises(ValidationError):
        request(**{DOC: [bad]})


# --- the store ---


def _moves(cursor):
    """The executed statements that move rows (UPDATE ... ingestion_id)."""
    return [
        c for c in cursor.execute.call_args_list
        if "UPDATE" in str(c.args[0]) and "ingestion_id = %s" in str(c.args[0])
    ]


@patch("src.core.vectorstore.pgvector_store.psycopg.connect")
def test_patch_and_move_run_first_in_the_same_connection(mock_connect):
    cursor = _cursor(mock_connect)
    # 1) move-and-patch returns chunk 0; 2) the plain retag moves what is left.
    cursor.fetchall.side_effect = [[(DOC, 0)], [(DOC,)]]
    store = PgVectorStore(dsn="mock", dimension=1024)

    result = store.retag_ingestion_id(
        [DOC], "new", expected_ingestion_id="old",
        source_ranges_by_document_id={DOC: [ok(0)]},
    )

    assert mock_connect.call_count == 1  # one connection, so one transaction
    texts = [str(c.args[0]) for c in cursor.execute.call_args_list]
    patch_ = next(i for i, t in enumerate(texts) if "start_line" in t)
    retag = next(
        i for i, t in enumerate(texts)
        if "SET ingestion_id" in t and "start_line" not in t
    )
    assert patch_ < retag  # a patched row is moved once, by the first statement
    assert result.ranges_patched == 1 and list(result.ranges_skipped) == []
    assert result.rows == 2  # one patched row plus one moved by the plain retag


@patch("src.core.vectorstore.pgvector_store.psycopg.connect")
def test_each_row_is_written_once_a_move_statement_per_batch_plus_one_plain(
    mock_connect,
):
    cursor = _cursor(mock_connect)
    cursor.fetchall.return_value = []
    store = PgVectorStore(dsn="mock", dimension=1024)
    store.RANGE_PATCH_BATCH = 2
    store.retag_ingestion_id(
        [DOC], "new", {DOC: {"role": "x"}}, expected_ingestion_id="old",
        source_ranges_by_document_id={DOC: [ok(i) for i in range(5)]},
    )
    moves = _moves(cursor)
    with_ranges = [c for c in moves if "start_line" in str(c.args[0])]
    plain = [c for c in moves if "start_line" not in str(c.args[0])]
    assert len(with_ranges) == 3  # 2 + 2 + 1 passages
    assert len(plain) == 1  # the leftover rows, retagged once (with provenance)


@patch("src.core.vectorstore.pgvector_store.psycopg.connect")
def test_move_and_patch_is_location_only_digest_and_generation_guarded(
    mock_connect,
):
    cursor = _cursor(mock_connect)
    cursor.fetchall.side_effect = [[(DOC, 0)], [(DOC,)]]
    store = PgVectorStore(dsn="mock", dimension=1024)
    store.retag_ingestion_id(
        [DOC], "new", expected_ingestion_id="old",
        source_ranges_by_document_id={DOC: [ok(0)]},
    )
    call = next(
        c for c in cursor.execute.call_args_list if "start_line" in str(c.args[0])
    )
    stmt, params = str(call.args[0]), call.args[1]
    set_clause = stmt.split("SET", 1)[1].split("FROM", 1)[0]
    # Only these two columns are written.
    written = set_clause.replace("source_metadata", "").replace("ingestion_id", "")
    for forbidden in ("vector", "chunk_text", "chunk_index", "chunk_id", "provider"):
        assert forbidden not in written
    for key in ("'start_line'", "'end_line'", "'range_reason'"):
        assert key in stmt
    # Guards: digest of the stored passage, and the EXPECTED (prior) generation.
    assert "sha256" in stmt and "vc.ingestion_id = %s" in stmt
    assert params[0] == "new" and params[-1] == "old"


@patch("src.core.vectorstore.pgvector_store.psycopg.connect")
def test_provenance_rides_the_same_statement_for_patched_rows(mock_connect):
    cursor = _cursor(mock_connect)
    cursor.fetchall.side_effect = [[(DOC, 0)], [], []]
    store = PgVectorStore(dsn="mock", dimension=1024)
    store.retag_ingestion_id(
        [DOC], "new", {DOC: {"role": "implementation"}},
        expected_ingestion_id="old",
        source_ranges_by_document_id={DOC: [ok(0)]},
    )
    stmt = next(
        str(c.args[0]) for c in cursor.execute.call_args_list
        if "start_line" in str(c.args[0])
    )
    assert "jsonb_set" in stmt  # provenance applied in the same write


@patch("src.core.vectorstore.pgvector_store.psycopg.connect")
def test_unmatched_patches_are_reported_with_a_reason_not_dropped(mock_connect):
    cursor = _cursor(mock_connect)
    # Move-and-patch moves chunk 0 only. The plain retag then moves chunk 1's row
    # (digest mismatch). Chunk 2 does not exist at the new generation.
    cursor.fetchall.side_effect = [[(DOC, 0)], [(DOC,)], [(DOC, 1)]]
    store = PgVectorStore(dsn="mock", dimension=1024)

    result = store.retag_ingestion_id(
        [DOC], "new", expected_ingestion_id="old",
        source_ranges_by_document_id={DOC: [ok(0), ok(1), ok(2)]},
    )

    assert result.ranges_patched == 1
    skipped = {(s["document_id"], s["chunk_index"]): s["reason"]
               for s in result.ranges_skipped}
    assert skipped == {
        (DOC, 1): "digest mismatch",
        (DOC, 2): "row not found at this generation",
    }


@patch("src.core.vectorstore.pgvector_store.psycopg.connect")
def test_bad_input_is_refused_before_any_sql(mock_connect):
    cursor = _cursor(mock_connect)
    store = PgVectorStore(dsn="mock", dimension=1024)
    bad_inputs = [
        {DOC2: [ok(0)]},  # a document that is not in document_ids
        {DOC: [ok(0), ok(0)]},  # the same passage twice
        {DOC: [{**ok(0), "text_sha256": "short"}]},
        {DOC: [{**ok(0), "start_line": 9, "end_line": 2}]},
    ]
    for bad in bad_inputs:
        with pytest.raises(ValueError):
            store.retag_ingestion_id(
                [DOC], "new", expected_ingestion_id="old",
                source_ranges_by_document_id=bad,
            )
    cursor.execute.assert_not_called()


@patch("src.core.vectorstore.pgvector_store.psycopg.connect")
def test_without_ranges_nothing_changes_for_existing_callers(mock_connect):
    cursor = _cursor(mock_connect)
    cursor.fetchall.return_value = [(DOC,)]
    store = PgVectorStore(dsn="mock", dimension=1024)
    result = store.retag_ingestion_id([DOC], "new", expected_ingestion_id="old")
    assert result.rows == 1
    assert result.ranges_patched == 0 and list(result.ranges_skipped) == []
    assert not any("start_line" in str(c.args[0])
                   for c in cursor.execute.call_args_list)


# --- the route ---


def test_route_passes_ranges_and_reports_counts_and_skips():
    store = MagicMock()
    store.retag_ingestion_id.return_value = MagicMock(
        rows=2, document_ids=[DOC], ranges_patched=1,
        ranges_skipped=[{"document_id": DOC, "chunk_index": 1,
                         "reason": "digest mismatch"}],
    )
    req = request(**{DOC: [ok(0), ok(1)]})

    import asyncio
    body = asyncio.run(retag_vectors(req, store))

    kwargs = store.retag_ingestion_id.call_args.kwargs
    assert kwargs["expected_ingestion_id"] == "old"
    assert set(kwargs["source_ranges_by_document_id"]) == {DOC}
    assert body["count"] == 2 and body["ranges_patched"] == 1
    assert body["ranges_skipped"] == [
        {"document_id": DOC, "chunk_index": 1, "reason": "digest mismatch"}
    ]
    assert body["ranges_skipped_total"] == 1


def test_route_without_ranges_does_not_pass_the_new_argument():
    store = MagicMock()
    store.retag_ingestion_id.return_value = MagicMock(
        rows=1, document_ids=[DOC], ranges_patched=0, ranges_skipped=[]
    )
    req = VectorRetagRequest(
        document_ids=[DOC], new_ingestion_id="new", expected_ingestion_id="old"
    )
    import asyncio
    asyncio.run(retag_vectors(req, store))
    sent = store.retag_ingestion_id.call_args.kwargs
    assert "source_ranges_by_document_id" not in sent
