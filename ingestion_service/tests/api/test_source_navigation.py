"""#379 deterministic source access: offline contract and budget tests."""

import json
import re
import uuid

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from src.api.errors import register_error_handlers
from src.api.v1 import source_navigation as api
from src.core import source_navigation as source

pytestmark = pytest.mark.unit


def test_source_identity_is_not_inferred_from_null_symbol_path():
    assert source.readable("a.py", "a.py", "python source", True)
    assert not source.readable("a.py#f", "a.py", "python source", True)
    assert not source.readable("a.py", "a.py", "file", True)
    assert not source.readable("a.py", "a.py", "python source", False)


def test_generation_is_mandatory_and_invalid_paths_fail_before_db(monkeypatch):
    monkeypatch.setattr(source, "snapshot", lambda: pytest.fail("DB accessed"))
    app = FastAPI()
    register_error_handlers(app)
    app.include_router(api.router, prefix="/v1")
    client = TestClient(app)
    base = f"/v1/repos/{uuid.uuid4()}/source/read"
    assert client.get(base).status_code == 400
    for path in ("../a.py", "/a.py", "C:/a.py", "a\\b.py", "a/./b.py"):
        response = client.get(
            base,
            params={
                "generation_id": str(uuid.uuid4()),
                "path": path,
            },
        )
        assert response.status_code == 400
        assert response.json()["error_code"] == "INVALID_REQUEST"


@pytest.mark.parametrize("value", ["", "a", "a\n", "\n\n", "é\n中\nlast", "a\r\nb\n"])
def test_ranges_reassemble_exact_lf_source(monkeypatch, value):
    monkeypatch.setattr(source, "WINDOW", 2)
    lines = value.splitlines(keepends=True)
    for start in range(1, len(lines) + 1):
        for end in range(start, len(lines) + 1):
            budget = source.Budget()
            actual, first, last, eof = source.scan_source(
                lambda offset, count: value[offset - 1 : offset - 1 + count],
                len(value.encode()),
                start,
                end,
                budget,
            )
            assert actual == "".join(lines[start - 1 : end])
            assert (first, last, eof) == (start, end, end == len(lines))
            assert budget.scanned <= source.MAX_SCAN


@pytest.mark.parametrize(
    "pattern,path,match",
    [
        ("**/*.py", "a.py", True),
        ("**/*.py", "x/y/a.py", True),
        ("*.py", "x/a.py", False),
        ("x/**/a?.py", "x/a1.py", True),
        ("x/**/a?.py", "x/y/z/a1.py", True),
        ("[1]%.py", "[1]%.py", True),
        ("[1]%.py", "1a.py", False),
        ("A.py", "a.py", False),
        ("**/é.py", "src/é.py", True),
    ],
)
def test_glob_is_segment_aware_and_other_characters_are_literal(pattern, path, match):
    assert bool(re.fullmatch(source.glob_regex(pattern), path)) is match


def test_cursors_bind_all_filters_and_reject_malformed_inputs():
    repo, gen = str(uuid.uuid4()), str(uuid.uuid4())
    cursor = source.encode_cursor(repo, gen, "**", "src/é.py")
    assert source.decode_cursor(cursor, repo, gen, "**") == "src/é.py"
    for args in (("other", gen, "**"), (repo, "other", "**"), (repo, gen, "*.py")):
        with pytest.raises(source.NavigationError) as err:
            source.decode_cursor(cursor, *args)
        assert err.value.status == 400
    for bad in ("!", "x" * 4097, "bnVsbA", "e30"):
        with pytest.raises(source.NavigationError):
            source.decode_cursor(bad, repo, gen, "**")


def test_budget_exhaustion_is_not_partial_source(monkeypatch):
    monkeypatch.setattr(source, "MAX_SCAN", 16)
    data = "x\n" * 100
    with pytest.raises(source.NavigationError) as err:
        source.scan_source(
            lambda offset, count: data[offset - 1 : offset - 1 + count],
            len(data),
            90,
            91,
            source.Budget(),
        )
    assert err.value.body["error_code"] == "SCAN_LIMIT_EXCEEDED"
    assert "text" not in err.value.body


def test_output_and_query_bounds(monkeypatch):
    monkeypatch.setattr(source, "MAX_TEXT", 8)
    with pytest.raises(source.NavigationError, match="text exceeds"):
        source.scan_source(lambda offset, count: "é" * 10, 20, 1, 1, source.Budget())
    budget = source.Budget()
    budget.queries = 32
    with pytest.raises(source.NavigationError) as err:
        budget.execute(None, None)
    assert err.value.body["error_code"] == "SCAN_LIMIT_EXCEEDED"


def test_actual_json_size_includes_escaping(monkeypatch):
    monkeypatch.setattr(source, "MAX_RESPONSE", 100)
    body = {"text": "\x01" * 20}
    assert len(body["text"].encode()) < 100
    assert len(json.dumps(body).encode()) > 100
    with pytest.raises(source.NavigationError) as err:
        source.serialize(body, source.Budget())
    assert err.value.body["error_code"] == "RESPONSE_TOO_LARGE"


def test_deadline_covers_processing_and_serialization(monkeypatch):
    clock = [0.0]
    monkeypatch.setattr(source, "monotonic", lambda: clock[0])
    budget = source.Budget()

    def slow_fetch(offset, count):
        clock[0] = 6
        return "x\n"

    with pytest.raises(source.NavigationError) as err:
        source.scan_source(slow_fetch, 2, 1, 1, budget)
    assert err.value.body["error_code"] == "DEADLINE_EXCEEDED"
    clock[0] = 0
    original = source.json.dumps

    def slow_serialize(*args, **kwargs):
        clock[0] = 6
        return original(*args, **kwargs)

    monkeypatch.setattr(source.json, "dumps", slow_serialize)
    with pytest.raises(source.NavigationError):
        source.serialize({"text": "x"}, budget)


def test_openapi_describes_generation_and_complete_source_response():
    app = FastAPI()
    app.include_router(api.router, prefix="/v1")
    schema = app.openapi()
    parameters = schema["paths"]["/v1/repos/{repo_id}/source/read"]["get"]["parameters"]
    assert next(p for p in parameters if p["name"] == "generation_id")["required"]
    assert (
        "text_sha256" in schema["components"]["schemas"]["ReadResponse"]["properties"]
    )


def test_byte_budget_bounds_multibyte_windows_before_fetch(monkeypatch):
    monkeypatch.setattr(source, "MAX_SCAN", 16)
    budget = source.Budget()
    assert budget.window_size() == 4
    budget.scanned = 12
    assert budget.window_size() == 1
    budget.scanned = 16
    with pytest.raises(source.NavigationError) as err:
        budget.window_size()
    assert err.value.body["error_code"] == "SCAN_LIMIT_EXCEEDED"


def test_database_timeout_tracks_remaining_operation_time(monkeypatch):
    clock = [0.0]
    monkeypatch.setattr(source, "monotonic", lambda: clock[0])
    budget = source.Budget()
    statements = []

    class Session:
        def execute(self, statement):
            statements.append(str(statement))
            return None

    clock[0] = 4
    budget.execute(Session(), "SELECT 1")
    assert statements[0] == "SET LOCAL statement_timeout = 1000"
    assert budget.queries == 1
    clock[0] = 5
    with pytest.raises(source.NavigationError):
        budget.execute(Session(), "SELECT 2")
    assert len(statements) == 3
