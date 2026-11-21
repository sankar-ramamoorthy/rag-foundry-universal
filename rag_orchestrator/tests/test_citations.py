# rag_orchestrator/tests/test_citations.py
"""
Issue #407 / specs/012-structured-citations: structured `citations` next to
the unchanged `sources`, one per passage in the final-context manifest.
Unit tests only: no network, database or model.
"""

import pytest
from fastapi.testclient import TestClient

from src.api.v1.main import app
from src.core import citations
from src.core.service import RAGResult
from src.retrieval.agent_adapter import build_final_context_manifest

pytestmark = pytest.mark.unit

GEN = "00000000-0000-4000-8000-000000000001"
REASON = "line span not persisted at ingestion"


def _entry(**kw):
    base = {
        "canonical_id": "a.py#foo",
        "document_id": "doc-1",
        "chunk_id": "chunk-1",
        "text_sha256": "f" * 64,
        "relative_path": "a.py",
    }
    base.update(kw)
    return base


def test_manifest_gains_relative_path():
    chunks = [
        {
            "text": "def foo(): pass",
            "document_id": "d1",
            "canonical_id": "a.py#foo",
            "metadata": {"source_metadata": {"relative_path": "a.py"}},
        },
        {"text": "x", "document_id": "d2", "metadata": {"relative_path": "b.py"}},
        {"text": "y", "document_id": "d3"},
    ]
    manifest = build_final_context_manifest(chunks)
    assert [m["relative_path"] for m in manifest] == ["a.py", "b.py", None]


def test_one_citation_per_manifest_entry_in_order():
    manifest = [_entry(), _entry(canonical_id="b.py#bar", relative_path="b.py")]
    out = citations.from_manifest("repo-x", GEN, manifest)
    assert [c.canonical_id for c in out] == ["a.py#foo", "b.py#bar"]
    first = out[0]
    assert (first.repo_id, first.generation_id) == ("repo-x", GEN)
    assert first.path == "a.py"
    assert first.document_id == "doc-1"
    assert first.chunk_id == "chunk-1"
    assert first.text_sha256 == "f" * 64


def test_ranges_are_null_with_a_reason_never_dropped():
    out = citations.from_manifest("repo-x", GEN, [_entry()])
    assert out[0].start_line is None and out[0].end_line is None
    assert out[0].range_reason == REASON


def test_passage_without_path_is_listed_with_null_path():
    out = citations.from_manifest("repo-x", GEN, [_entry(relative_path=None)])
    assert len(out) == 1 and out[0].path is None


def test_missing_manifest_gives_empty_list():
    assert citations.from_manifest("repo-x", GEN, None) == []
    assert citations.from_manifest("repo-x", GEN, []) == []


def test_inventory_citation_uses_verified_whole_file_digest():
    plan = {
        "generation_id": GEN,
        "strategy": "python_inventory",
        "completion": "verified_complete",
        "returned_text_sha256": "e" * 64,
    }
    out = citations.from_inventory("repo-x", plan, ["x.py"])
    assert len(out) == 1
    assert out[0].path == "x.py" and out[0].text_sha256 == "e" * 64
    assert out[0].canonical_id is None and out[0].chunk_id is None
    incomplete = {**plan, "completion": "incomplete"}
    assert citations.from_inventory("repo-x", incomplete, ["x.py"]) == []


# --- HTTP ---


def _patch_rag(monkeypatch, plan, sources=("s",)):
    import src.api.v1.routes as routes

    async def no_inventory(query):
        return None

    async def fake_run_rag(**kwargs):
        return RAGResult(
            answer="a", sources=list(sources), repo_id="repo-x", retrieval_plan=plan
        )

    monkeypatch.setattr(routes, "inventory_response", no_inventory)
    monkeypatch.setattr(routes, "run_rag", fake_run_rag)


def test_rag_response_has_citations_and_unchanged_sources(monkeypatch):
    plan = {
        "generation_id": GEN,
        "final_context_manifest": [_entry(), _entry(canonical_id="b.py#bar")],
    }
    _patch_rag(monkeypatch, plan)
    body = TestClient(app).post(
        "/v1/rag", json={"query": "q", "repo_id": "repo-x"}
    ).json()
    assert body["sources"] == ["s"]
    assert len(body["citations"]) == 2
    assert body["citations"][0]["generation_id"] == GEN
    assert body["citations"][0]["range_reason"] == REASON


def test_rag_without_manifest_has_empty_citations(monkeypatch):
    _patch_rag(monkeypatch, {"generation_id": GEN})
    body = TestClient(app).post(
        "/v1/rag", json={"query": "q", "repo_id": "repo-x"}
    ).json()
    assert body["citations"] == []


def test_rag_inventory_path_cites_the_file(monkeypatch):
    import src.api.v1.routes as routes
    from src.api.v1.models import RAGResponse

    async def inventory(query):
        return RAGResponse(
            answer="2 functions",
            sources=["x.py"],
            repo_id="repo-x",
            retrieval_plan={
                "generation_id": GEN,
                "strategy": "python_inventory",
                "completion": "verified_complete",
                "returned_text_sha256": "e" * 64,
            },
        )

    monkeypatch.setattr(routes, "inventory_response", inventory)
    body = TestClient(app).post(
        "/v1/rag", json={"query": "What functions are in x.py?", "repo_id": "repo-x"}
    ).json()
    assert [c["path"] for c in body["citations"]] == ["x.py"]
    assert body["citations"][0]["text_sha256"] == "e" * 64


# --- issue #412: persisted ranges flow through, never guessed ---


def test_manifest_carries_persisted_range_flat_and_nested():
    chunks = [
        {
            "text": "x",
            "document_id": "d1",
            "metadata": {"start_line": 3, "end_line": 8, "relative_path": "a.py"},
        },
        {
            "text": "y",
            "document_id": "d2",
            "metadata": {
                "source_metadata": {
                    "relative_path": "b.py",
                    "range_reason": "artifact split into several passages",
                }
            },
        },
        {"text": "z", "document_id": "d3"},
    ]
    manifest = build_final_context_manifest(chunks)
    assert (manifest[0]["start_line"], manifest[0]["end_line"]) == (3, 8)
    assert manifest[1]["start_line"] is None
    assert manifest[1]["range_reason"] == "artifact split into several passages"
    assert manifest[2]["range_reason"] is None


def test_citation_uses_a_well_formed_persisted_range():
    out = citations.from_manifest(
        "repo-x", GEN, [_entry(start_line=3, end_line=8, range_reason=None)]
    )
    assert (out[0].start_line, out[0].end_line) == (3, 8)
    assert out[0].range_reason is None


def test_citation_keeps_the_stored_reason_when_there_is_no_range():
    out = citations.from_manifest(
        "repo-x", GEN, [_entry(range_reason="passage split; range not established")]
    )
    assert out[0].start_line is None
    assert out[0].range_reason == "passage split; range not established"


@pytest.mark.parametrize(
    "start,end", [(0, 3), (5, 2), ("3", 8), (3, None), (True, 5)]
)
def test_malformed_range_is_never_repaired(start, end):
    out = citations.from_manifest(
        "repo-x", GEN, [_entry(start_line=start, end_line=end)]
    )
    assert out[0].start_line is None and out[0].end_line is None
    assert out[0].range_reason == REASON


# --- issue #416 WP5: every reason in spec 015 passes through unchanged ---

SPEC_015_REASONS = [
    "artifact range not verified",
    "window offset not reported",
    "passage does not match artifact text at reported offset",
    "passage split; range not established",
    "line span not persisted at ingestion",
    # Retired for new generations; rows written before #416 keep it.
    "artifact split into several passages",
]


@pytest.mark.parametrize("reason", SPEC_015_REASONS)
def test_every_spec_reason_is_returned_unchanged_with_no_range(reason):
    manifest = build_final_context_manifest(
        [
            {
                "text": "x",
                "document_id": "d1",
                "metadata": {
                    "source_metadata": {
                        "relative_path": "a.py",
                        "range_reason": reason,
                    }
                },
            }
        ]
    )
    out = citations.from_manifest("repo-x", GEN, manifest)
    assert out[0].start_line is None and out[0].end_line is None
    assert out[0].range_reason == reason


def test_a_window_range_flows_from_chunk_metadata_to_the_http_citation(monkeypatch):
    chunk = {
        "text": "window text",
        "document_id": "d1",
        "canonical_id": "a.py#f",
        "metadata": {
            "source_metadata": {
                "relative_path": "a.py",
                "start_line": 40,
                "end_line": 52,
            }
        },
    }
    plan = {
        "generation_id": GEN,
        "final_context_manifest": build_final_context_manifest([chunk]),
    }
    _patch_rag(monkeypatch, plan)
    body = TestClient(app).post(
        "/v1/rag", json={"query": "q", "repo_id": "repo-x"}
    ).json()
    cited = body["citations"][0]
    assert (cited["path"], cited["start_line"], cited["end_line"]) == ("a.py", 40, 52)
    assert cited["range_reason"] is None
    assert cited["generation_id"] == GEN
