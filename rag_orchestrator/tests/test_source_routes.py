# rag_orchestrator/tests/test_source_routes.py
"""
Issue #408 / specs/013-orchestrator-read-and-locate: read and locate through
the orchestrator. Mocked ingestion service; no network, database or model.
"""

import hashlib

import httpx
import pytest
from fastapi.testclient import TestClient

from src.api.v1.main import app
from src.core import execution_policy

pytestmark = pytest.mark.unit

REPO = "00000000-0000-4000-8000-000000000001"
GEN = "00000000-0000-4000-8000-000000000002"
SOURCE = "def a():\n    pass\n\n\nclass C:\n    def m(self):\n        pass\n"
SHA = "b" * 40


def _sha(text):
    return hashlib.sha256(text.encode()).hexdigest()


class Ingestion:
    """Minimal fake of the ingestion service's generation, files and read."""

    def __init__(self, files=None, corrupt=False, generation=GEN):
        self.files = files if files is not None else [("pkg/mod.py", "python source")]
        self.corrupt = corrupt
        self.generation = generation
        self.calls = []

    def __call__(self, request: httpx.Request) -> httpx.Response:
        path, params = request.url.path, request.url.params
        self.calls.append((path, dict(params)))
        if path.endswith("/generation"):
            return httpx.Response(
                200,
                json={"ingestion_id": self.generation, "generation_status": "ready"},
            )
        if params.get("generation_id") not in (None, self.generation):
            return httpx.Response(
                409, json={"error_code": "GENERATION_MISMATCH", "message": "m"}
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
                            "path": p,
                            "canonical_id": p,
                            "document_id": f"doc-{i}",
                            "doc_type": t,
                            "source_status": "available",
                        }
                        for i, (p, t) in enumerate(self.files)
                    ],
                    "next_cursor": None,
                },
            )
        if path.endswith("/source/read"):
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
                    "returned_text_sha256": "0" * 64 if self.corrupt else _sha(text),
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


# --- files ---


def test_files_proxy_adds_envelope_and_keeps_body(monkeypatch):
    backend = Ingestion()
    client = _serve(monkeypatch, backend)
    body = client.get(
        f"/v1/repos/{REPO}/source/files",
        params={"generation_id": GEN, "pattern": "**/*.py"},
    ).json()
    env = body.pop("envelope")
    assert body["files"][0]["path"] == "pkg/mod.py"
    assert body["commit_sha"] == SHA
    assert env["generation_id"] == GEN and env["commit_sha"] == SHA
    assert env["coverage"] == "complete"
    sent = [c for c in backend.calls if c[0].endswith("/source/files")][0][1]
    assert sent["pattern"] == "**/*.py"


def test_omitted_generation_is_resolved_once(monkeypatch):
    client = _serve(monkeypatch, Ingestion())
    body = client.get(f"/v1/repos/{REPO}/source/files").json()
    assert body["envelope"]["generation_id"] == GEN


def test_stale_generation_error_is_returned_unchanged(monkeypatch):
    client = _serve(monkeypatch, Ingestion())
    response = client.get(
        f"/v1/repos/{REPO}/source/files", params={"generation_id": "other"}
    )
    assert response.status_code == 409
    assert response.json()["error_code"] == "GENERATION_MISMATCH"


def test_unreachable_ingestion_is_502(monkeypatch):
    def boom(request):
        raise httpx.ConnectError("down")

    client = _serve(monkeypatch, boom)
    response = client.get(
        f"/v1/repos/{REPO}/source/files", params={"generation_id": GEN}
    )
    assert response.status_code == 502


# --- read ---


def test_read_returns_same_text_and_digest(monkeypatch):
    client = _serve(monkeypatch, Ingestion())
    body = client.get(
        f"/v1/repos/{REPO}/source/read",
        params={"generation_id": GEN, "path": "pkg/mod.py"},
    ).json()
    assert body["text"] == SOURCE
    assert body["returned_text_sha256"] == _sha(SOURCE)
    assert body["envelope"]["generation_id"] == GEN
    assert body["envelope"]["coverage"] == "complete"


def test_partial_read_is_partial_coverage(monkeypatch):
    client = _serve(monkeypatch, Ingestion())
    body = client.get(
        f"/v1/repos/{REPO}/source/read",
        params={
            "generation_id": GEN,
            "path": "pkg/mod.py",
            "start_line": 1,
            "end_line": 2,
        },
    ).json()
    assert body["envelope"]["coverage"] == "partial"
    assert any("continues at line 3" in n for n in body["envelope"]["limitations"])


def test_read_digest_mismatch_is_502(monkeypatch):
    client = _serve(monkeypatch, Ingestion(corrupt=True))
    response = client.get(
        f"/v1/repos/{REPO}/source/read",
        params={"generation_id": GEN, "path": "pkg/mod.py"},
    )
    assert response.status_code == 502


# --- locate ---


def test_locate_python_file_matches_whole_module_ast(monkeypatch):
    client = _serve(monkeypatch, Ingestion())
    body = client.get(
        f"/v1/repos/{REPO}/locate",
        params={"query": "pkg/mod.py", "generation_id": GEN},
    ).json()
    candidate = body["candidates"][0]
    expected = [
        {"name": r["name"], "start_line": r["start"], "end_line": r["end"]}
        for r in execution_policy.inventory(SOURCE)
    ]
    got = [
        {k: d[k] for k in ("name", "start_line", "end_line")}
        for d in candidate["definitions"]
    ]
    assert got == expected and len(got) == 2
    assert candidate["definitions_status"] == "verified_complete"
    assert candidate["match"] == "glob"
    assert body["envelope"]["coverage"] == "complete"
    assert body["envelope"]["generation_id"] == GEN


def test_locate_basename_uses_double_star_glob(monkeypatch):
    backend = Ingestion()
    client = _serve(monkeypatch, backend)
    body = client.get(
        f"/v1/repos/{REPO}/locate", params={"query": "mod.py", "generation_id": GEN}
    ).json()
    assert body["candidates"][0]["match"] == "basename"
    sent = [c for c in backend.calls if c[0].endswith("/source/files")][0][1]
    assert sent["pattern"] == "**/mod.py"


def test_locate_other_language_is_not_covered_not_empty(monkeypatch):
    backend = Ingestion(files=[("web/app.ts", "typescript source")])
    client = _serve(monkeypatch, backend)
    body = client.get(
        f"/v1/repos/{REPO}/locate",
        params={"query": "web/app.ts", "generation_id": GEN},
    ).json()
    candidate = body["candidates"][0]
    assert candidate["definitions"] is None
    assert candidate["definitions_status"] == "not_covered_language"
    assert body["envelope"]["coverage"] == "partial"


def test_locate_no_match_is_200_with_limitation(monkeypatch):
    client = _serve(monkeypatch, Ingestion(files=[]))
    response = client.get(
        f"/v1/repos/{REPO}/locate", params={"query": "nope.py", "generation_id": GEN}
    )
    assert response.status_code == 200
    body = response.json()
    assert body["candidates"] == []
    assert any("no file matched" in n for n in body["envelope"]["limitations"])


def test_locate_without_definitions_makes_no_reads(monkeypatch):
    backend = Ingestion()
    client = _serve(monkeypatch, backend)
    body = client.get(
        f"/v1/repos/{REPO}/locate",
        params={
            "query": "pkg/mod.py",
            "generation_id": GEN,
            "include_definitions": "false",
        },
    ).json()
    assert body["candidates"][0]["definitions_status"] == "not_requested"
    assert not [c for c in backend.calls if c[0].endswith("/source/read")]


def test_locate_states_what_it_does_not_search(monkeypatch):
    client = _serve(monkeypatch, Ingestion())
    body = client.get(
        f"/v1/repos/{REPO}/locate", params={"query": "pkg/mod.py", "generation_id": GEN}
    ).json()
    assert any("semantic" in n for n in body["envelope"]["limitations"])


def test_locate_rejects_non_uuid_repo(monkeypatch):
    client = _serve(monkeypatch, Ingestion())
    response = client.get("/v1/repos/not-a-uuid/locate", params={"query": "x.py"})
    assert response.status_code == 400
