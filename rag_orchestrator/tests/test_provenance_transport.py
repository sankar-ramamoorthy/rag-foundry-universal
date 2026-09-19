# rag_orchestrator/tests/test_provenance_transport.py
"""
Issue #199, Stage B2: provenance is transport-only through the retrieval
path -- DocumentNode.provenance (Stage B1) -> chunk metadata -> vector
search response -> RetrievedChunk -> agent chunk dict -> final-context
manifest. No ranking, filtering, source-preference, sufficiency-policy,
prompt-policy, or generation-behavior change; these tests assert
provenance reaches each hop unchanged and assert nothing about
selection/ordering/text changing because of it.
"""

import pytest

from src.core.service import _add_chunks
from src.retrieval.agent_adapter import (
    build_final_context_manifest,
    prepare_chunks_for_agent,
)
from src.retrieval.codebase_utils import provenance_from_metadata
from src.retrieval.types import RetrievedChunk, RetrievedContext

pytestmark = pytest.mark.unit

_PROVENANCE = {
    "role": {"value": "implementation", "basis": "doc_type:source_suffix"},
    "subject": {"value": "selected_repository", "basis": None},
    "derivation": {"status": "source"},
    "validity": {"declared_status": "unknown"},
    "classification": {
        "schema_version": "provenance-v1",
        "classifier_version": "role-subject-v1",
        "scope": "artifact",
    },
}


# --- provenance_from_metadata: same lookup shape as canonical_id/doc_type ---


def test_provenance_from_metadata_flat():
    assert provenance_from_metadata({"provenance": _PROVENANCE}) == _PROVENANCE


def test_provenance_from_metadata_nested_under_source_metadata():
    metadata = {"source_metadata": {"provenance": _PROVENANCE}}
    assert provenance_from_metadata(metadata) == _PROVENANCE


def test_provenance_from_metadata_absent_is_none_not_guessed():
    assert provenance_from_metadata({}) is None
    assert provenance_from_metadata({"source_metadata": {}}) is None


# --- vector search response -> RetrievedChunk ---


def test_add_chunks_populates_retrieved_chunk_provenance():
    results = [
        {
            "chunk_id": "c1",
            "text": "def foo(): ...",
            "score": 0.9,
            "metadata": {
                "canonical_id": "a.py#foo",
                "source_metadata": {"provenance": _PROVENANCE},
            },
        }
    ]
    added = _add_chunks("doc-1", results, set(), {})
    assert len(added) == 1
    assert added[0].provenance == _PROVENANCE
    # Transport only: canonical_id/text/score are exactly what they were
    # before this field existed.
    assert added[0].canonical_id == "a.py#foo"
    assert added[0].text == "def foo(): ..."


def test_add_chunks_missing_provenance_is_none_not_an_error():
    results = [
        {"chunk_id": "c1", "text": "x", "score": 0.5, "metadata": {}},
    ]
    added = _add_chunks("doc-1", results, set(), {})
    assert added[0].provenance is None


# --- RetrievedChunk -> agent chunk dict -> final-context manifest ---


def test_prepare_chunks_for_agent_carries_provenance_through():
    chunk = RetrievedChunk(
        chunk_id="c1",
        document_id="doc-1",
        text="def foo(): ...",
        score=0.9,
        metadata={},
        canonical_id="a.py#foo",
        provenance=_PROVENANCE,
    )
    retrieved = RetrievedContext(chunks_by_document={"doc-1": [chunk]})
    agent_chunks = prepare_chunks_for_agent(retrieved, document_order=["doc-1"])
    assert agent_chunks[0]["provenance"] == _PROVENANCE


def test_prepare_chunks_for_agent_none_provenance_stays_none():
    chunk = RetrievedChunk(
        chunk_id="c1",
        document_id="doc-1",
        text="x",
        score=0.5,
        metadata={},
    )
    retrieved = RetrievedContext(chunks_by_document={"doc-1": [chunk]})
    agent_chunks = prepare_chunks_for_agent(retrieved, document_order=["doc-1"])
    assert agent_chunks[0]["provenance"] is None


def test_build_final_context_manifest_includes_provenance():
    chunks_in_final_context = [
        {
            "text": "def foo(): ...",
            "document_id": "doc-1",
            "chunk_id": "c1",
            "chunk_index": 0,
            "canonical_id": "a.py#foo",
            "fetch_position": 0,
            "provenance": _PROVENANCE,
        }
    ]
    manifest = build_final_context_manifest(
        chunks_in_final_context, seed_document_ids={"doc-1"}
    )
    assert len(manifest) == 1
    assert manifest[0]["provenance"] == _PROVENANCE
    # Transport only: selection_reason logic is untouched by provenance.
    assert manifest[0]["selection_reason"] == "seed"


def test_build_final_context_manifest_provenance_does_not_affect_selection():
    """A chunk with no provenance and a chunk with provenance are
    selected/ordered identically -- provenance is inert data, never a
    selection input, at this stage."""
    chunks_in_final_context = [
        {
            "text": "a",
            "document_id": "doc-1",
            "chunk_id": "c1",
            "canonical_id": "a.py#foo",
            "provenance": _PROVENANCE,
        },
        {
            "text": "b",
            "document_id": "doc-2",
            "chunk_id": "c2",
            "canonical_id": "b.py#bar",
            "provenance": None,
        },
    ]
    manifest = build_final_context_manifest(
        chunks_in_final_context, seed_document_ids={"doc-1", "doc-2"}
    )
    assert [m["chunk_id"] for m in manifest] == ["c1", "c2"]
    assert [m["selection_reason"] for m in manifest] == ["seed", "seed"]
