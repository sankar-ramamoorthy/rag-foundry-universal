"""Check generation fencing and byte comparison in the snapshot verifier."""

import hashlib
import importlib.util
from pathlib import Path

import pytest


MODULE_PATH = (
    Path(__file__).resolve().parents[1] / "scripts/verify_repo_compose_snapshot.py"
)
SPEC = importlib.util.spec_from_file_location(
    "verify_repo_compose_snapshot", MODULE_PATH
)
assert SPEC is not None and SPEC.loader is not None
verifier = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(verifier)


def _responses(content: bytes) -> tuple[dict, dict]:
    generation = {
        "repo_id": "repo",
        "ingestion_id": "generation",
        "generation_status": "ready",
        "commit_sha": "a" * 40,
    }
    snapshot = {
        **generation,
        "compose_documents": {
            "docker-compose.yml": {"sha256": hashlib.sha256(content).hexdigest()}
        },
    }
    return generation, snapshot


def test_verifies_pinned_source_bytes(monkeypatch, tmp_path):
    content = b"services:\n  app:\n    image: busybox\n"
    generation, snapshot = _responses(content)
    responses = iter((generation, snapshot, generation))
    monkeypatch.setattr(verifier, "_get_json", lambda _url: next(responses))
    monkeypatch.setattr(verifier, "_git_bytes", lambda *_args: content)
    result = verifier.verify_snapshot("http://example", "repo", "generation", tmp_path)
    assert result["verified"]
    assert result["files"][0]["matches"]


def test_reports_mismatched_bytes(monkeypatch, tmp_path):
    generation, snapshot = _responses(b"original")
    responses = iter((generation, snapshot, generation))
    monkeypatch.setattr(verifier, "_get_json", lambda _url: next(responses))
    monkeypatch.setattr(verifier, "_git_bytes", lambda *_args: b"changed")
    result = verifier.verify_snapshot("http://example", "repo", "generation", tmp_path)
    assert not result["verified"]
    assert not result["files"][0]["matches"]


def test_rejects_generation_change(monkeypatch, tmp_path):
    generation, snapshot = _responses(b"content")
    changed = {**generation, "ingestion_id": "next"}
    responses = iter((generation, snapshot, changed))
    monkeypatch.setattr(verifier, "_get_json", lambda _url: next(responses))
    monkeypatch.setattr(verifier, "_git_bytes", lambda *_args: b"content")
    with pytest.raises(ValueError, match="changed during verification"):
        verifier.verify_snapshot("http://example", "repo", "generation", tmp_path)


@pytest.mark.parametrize("path", ["../secret", "/absolute", "a\\b", "a:b"])
def test_rejects_unsafe_paths(path, tmp_path):
    with pytest.raises(ValueError, match="Unsafe snapshot path"):
        verifier._git_bytes(tmp_path, "a" * 40, path)
