# rag_orchestrator/tests/test_product_routes.py
"""
Issue #432 / specs/016-product-frontend: the product API's read side.
Mocked ingestion service; no network, database or model.
"""

import hashlib

import httpx
import pytest
from fastapi.testclient import TestClient

from src.api.v1.main import app

pytestmark = pytest.mark.unit

REPO = "00000000-0000-4000-8000-000000000001"
GEN = "00000000-0000-4000-8000-000000000002"
OTHER = "00000000-0000-4000-8000-000000000003"
SOURCE = "def a():\n    pass\n\n\nclass C:\n    def m(self):\n        pass\n"
SHA = "b" * 40

REPO_FIELDS = {
    "repo_id",
    "name",
    "display_name",
    "source_type",
    "branch",
    "ingested_at",
    "file_count",
    "node_count",
}


def _sha(text):
    return hashlib.sha256(text.encode()).hexdigest()


class Ingestion:
    def __init__(self, generation=GEN, status="ready", read_error=None):
        self.generation = generation
        self.status = status
        self.read_error = read_error
        self.calls = []

    def __call__(self, request: httpx.Request) -> httpx.Response:
        path, params = request.url.path, request.url.params
        self.calls.append((path, dict(params)))
        if path == "/v1/repos":
            return httpx.Response(
                200,
                json=[
                    {
                        "id": REPO,
                        "name": "demo",
                        "display_name": "acme/demo",
                        "status": "complete",
                        "ingestion_id": GEN,
                        "ingested_at": "2026-11-20T10:00:00Z",
                        "file_count": 3,
                        "node_count": 9,
                        "source_type": "git",
                        "git_url": "https://user:secret@example.com/acme/demo.git",
                        "local_path": "C:/Users/someone/private/demo",
                        "branch": "main",
                    }
                ],
            )
        if path.endswith("/generation"):
            return httpx.Response(
                200,
                json={
                    "repo_id": REPO,
                    "ingestion_id": self.generation if self.status == "ready" else None,
                    "generation_status": self.status,
                    "commit_sha": SHA if self.status == "ready" else None,
                    "ingested_at": "2026-11-20T10:00:00Z",
                    "is_incremental": False,
                },
            )
        if path.endswith("/orient"):
            return httpx.Response(
                200,
                json={
                    "repo_id": REPO,
                    "ingestion_id": self.generation,
                    "generation_status": "ready",
                    "commit_sha": SHA,
                    "languages": {"python": 3},
                    "file_counts": {"indexed": 3, "non_indexed": 0, "total": 3},
                    "manifests": [{"kind": "pyproject", "path": "pyproject.toml"}],
                    "services": [],
                    "test_dirs": ["tests"],
                    "docs_dirs": [],
                    "heuristic_fields": ["test_dirs"],
                    "gaps": [],
                    "computed_at": "2026-11-20T10:00:00Z",
                },
            )
        if params.get("generation_id") not in (None, self.generation):
            return httpx.Response(
                409,
                json={
                    "error_code": "GENERATION_MISMATCH",
                    "message": "generation is not current",
                    "details": {},
                },
            )
        if path.endswith("/source/files"):
            return httpx.Response(
                200,
                json={
                    "repo_id": REPO,
                    "generation_id": self.generation,
                    "commit_sha": SHA,
                    "files": [
                        {
                            "path": "pkg/mod.py",
                            "canonical_id": "pkg/mod.py",
                            "document_id": "doc-0",
                            "doc_type": "python source",
                            "source_status": "available",
                        }
                    ],
                    "next_cursor": None,
                },
            )
        if path.endswith("/source/read"):
            if self.read_error:
                status, code = self.read_error
                return httpx.Response(
                    status, json={"error_code": code, "message": "m", "details": {}}
                )
            lines = SOURCE.splitlines(keepends=True)
            start = int(params.get("start_line", 1))
            end = min(int(params.get("end_line", len(lines))), len(lines))
            text = "".join(lines[start - 1 : end])
            eof = end == len(lines)
            return httpx.Response(
                200,
                json={
                    "repo_id": REPO,
                    "generation_id": self.generation,
                    "commit_sha": SHA,
                    "path": params["path"],
                    "canonical_id": params["path"],
                    "document_id": "doc-0",
                    "doc_type": "python source",
                    "representation": "stored_source",
                    "start_line": start,
                    "end_line": end,
                    "complete_file": start == 1 and eof,
                    "next_start_line": None if eof else end + 1,
                    "text": text,
                    "returned_text_sha256": _sha(text),
                    "text_sha256": None,
                    "total_lines": end if eof else None,
                },
            )
        return httpx.Response(404)


def _serve(monkeypatch, backend):
    real = httpx.AsyncClient

    def patched(*args, **kwargs):
        kwargs["transport"] = httpx.MockTransport(backend)
        return real(*args, **kwargs)

    monkeypatch.setattr(httpx, "AsyncClient", patched)
    return TestClient(app)


def _error(response, code, status):
    assert response.status_code == status, response.text
    body = response.json()
    assert set(body) == {"error"}
    assert body["error"]["code"] == code
    assert set(body["error"]) == {"code", "message", "details"}


# --- repository picker ---


def test_repo_list_is_sanitized(monkeypatch):
    client = _serve(monkeypatch, Ingestion())
    response = client.get("/v1/product/repos")
    assert response.status_code == 200
    (repo,) = response.json()["repos"]
    assert set(repo) == REPO_FIELDS
    assert repo["repo_id"] == REPO and repo["display_name"] == "acme/demo"
    text = response.text
    assert "secret" not in text and "private" not in text and "example.com" not in text


def test_readiness_returns_generation_and_commit(monkeypatch):
    client = _serve(monkeypatch, Ingestion())
    body = client.get(f"/v1/product/repos/{REPO}/readiness").json()
    assert body["status"] == "ready"
    assert body["generation_id"] == GEN and body["commit_sha"] == SHA


def test_readiness_without_ready_generation_is_unavailable(monkeypatch):
    client = _serve(monkeypatch, Ingestion(status="unknown"))
    _error(client.get(f"/v1/product/repos/{REPO}/readiness"), "unavailable", 503)


def test_readiness_rejects_non_uuid(monkeypatch):
    client = _serve(monkeypatch, Ingestion())
    _error(client.get("/v1/product/repos/not-a-uuid/readiness"), "invalid_request", 400)


# --- orient ---


def test_orient_is_typed_and_pinned(monkeypatch):
    client = _serve(monkeypatch, Ingestion())
    body = client.get(
        f"/v1/product/repos/{REPO}/orient", params={"generation_id": GEN}
    ).json()
    assert body["generation_id"] == GEN
    assert body["languages"] == {"python": 3}
    assert body["envelope"]["generation_id"] == GEN


def test_orient_for_other_generation_is_stale(monkeypatch):
    client = _serve(monkeypatch, Ingestion())
    response = client.get(
        f"/v1/product/repos/{REPO}/orient", params={"generation_id": OTHER}
    )
    _error(response, "stale", 409)
    assert response.json()["error"]["details"]["current_generation_id"] == GEN


def test_generation_is_required(monkeypatch):
    client = _serve(monkeypatch, Ingestion())
    assert client.get(f"/v1/product/repos/{REPO}/orient").status_code == 422


# --- files and locate ---


def test_files_are_typed(monkeypatch):
    client = _serve(monkeypatch, Ingestion())
    body = client.get(
        f"/v1/product/repos/{REPO}/files",
        params={"generation_id": GEN, "pattern": "**/*.py"},
    ).json()
    assert body["files"][0]["path"] == "pkg/mod.py"
    assert body["envelope"]["commit_sha"] == SHA


def test_files_for_other_generation_is_stale(monkeypatch):
    client = _serve(monkeypatch, Ingestion())
    response = client.get(
        f"/v1/product/repos/{REPO}/files", params={"generation_id": OTHER}
    )
    _error(response, "stale", 409)


def test_locate_is_typed_with_definition_coverage(monkeypatch):
    client = _serve(monkeypatch, Ingestion())
    body = client.get(
        f"/v1/product/repos/{REPO}/locate",
        params={"generation_id": GEN, "query": "mod.py", "include_definitions": False},
    ).json()
    (candidate,) = body["candidates"]
    assert candidate["match"] == "basename"
    assert candidate["definitions"] is None
    assert candidate["definitions_status"] == "not_requested"


def test_locate_limit_out_of_range_is_invalid_request(monkeypatch):
    client = _serve(monkeypatch, Ingestion())
    response = client.get(
        f"/v1/product/repos/{REPO}/locate",
        params={"generation_id": GEN, "query": "x", "limit": 500},
    )
    _error(response, "invalid_request", 400)


# --- source read ---


def test_source_read_is_inclusive_and_pinned(monkeypatch):
    backend = Ingestion()
    client = _serve(monkeypatch, backend)
    body = client.get(
        f"/v1/product/repos/{REPO}/source",
        params={
            "generation_id": GEN,
            "path": "pkg/mod.py",
            "start_line": 1,
            "end_line": 2,
        },
    ).json()
    assert (body["start_line"], body["end_line"]) == (1, 2)
    assert body["text"] == "def a():\n    pass\n"
    assert body["complete_file"] is False and body["next_start_line"] == 3
    sent = [c for c in backend.calls if c[0].endswith("/source/read")][0][1]
    assert sent["generation_id"] == GEN


def test_source_read_other_generation_is_stale_and_returns_no_text(monkeypatch):
    client = _serve(monkeypatch, Ingestion())
    response = client.get(
        f"/v1/product/repos/{REPO}/source",
        params={"generation_id": OTHER, "path": "pkg/mod.py"},
    )
    _error(response, "stale", 409)
    assert "def a" not in response.text


@pytest.mark.parametrize(
    "params",
    [
        {"start_line": 0},
        {"start_line": 5, "end_line": 2},
        {"end_line": 0},
    ],
)
def test_source_read_invalid_interval_is_rejected_locally(monkeypatch, params):
    backend = Ingestion()
    client = _serve(monkeypatch, backend)
    response = client.get(
        f"/v1/product/repos/{REPO}/source",
        params={"generation_id": GEN, "path": "pkg/mod.py", **params},
    )
    _error(response, "invalid_range", 416)
    assert not [c for c in backend.calls if c[0].endswith("/source/read")]


@pytest.mark.parametrize(
    "upstream, code, status",
    [
        ((416, "INVALID_LINE_RANGE"), "invalid_range", 416),
        ((413, "READ_TOO_LARGE"), "resource_limit", 413),
        ((413, "RESPONSE_TOO_LARGE"), "resource_limit", 413),
        ((503, "DEADLINE_EXCEEDED"), "resource_limit", 503),
        ((404, "FILE_NOT_FOUND"), "not_found", 404),
        ((503, "SOURCE_UNAVAILABLE"), "unavailable", 503),
    ],
)
def test_source_errors_map_to_stable_codes(monkeypatch, upstream, code, status):
    client = _serve(monkeypatch, Ingestion(read_error=upstream))
    response = client.get(
        f"/v1/product/repos/{REPO}/source",
        params={"generation_id": GEN, "path": "pkg/mod.py"},
    )
    _error(response, code, status)


def test_existing_routes_are_unchanged(monkeypatch):
    client = _serve(monkeypatch, Ingestion())
    body = client.get(
        f"/v1/repos/{REPO}/source/files", params={"generation_id": GEN}
    ).json()
    assert "envelope" in body and "files" in body
    assert "error" not in body
