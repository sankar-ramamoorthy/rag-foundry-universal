# rag_orchestrator/tests/test_build_sources.py
"""
Issue #30 Part 4: RAG sources are canonical IDs / paths, not a wall of
duplicated document UUIDs.
"""
import pytest

from src.retrieval.agent_adapter import build_sources

pytestmark = pytest.mark.unit


def chunk(document_id, canonical_id=None, relative_path=None):
    metadata = {}
    if canonical_id:
        metadata["canonical_id"] = canonical_id
    if relative_path:
        metadata["relative_path"] = relative_path
    return {
        "text": "x",
        "document_id": document_id,
        "chunk_id": "c",
        "metadata": metadata,
    }


def test_canonical_id_preferred_over_path_and_uuid():
    chunks = [chunk("uuid-1", canonical_id="src/service.py#run_rag",
                    relative_path="src/service.py")]
    assert build_sources(chunks) == ["src/service.py#run_rag"]


def test_relative_path_fallback_then_document_id():
    chunks = [
        chunk("uuid-1", relative_path="docs/readme.md"),
        chunk("uuid-2"),
    ]
    assert build_sources(chunks) == ["docs/readme.md", "uuid-2"]


def test_duplicates_collapse_preserving_first_seen_order():
    chunks = [
        chunk("uuid-1", canonical_id="a.py#f"),
        chunk("uuid-1", canonical_id="a.py#f"),
        chunk("uuid-2", canonical_id="b.py"),
        chunk("uuid-1", canonical_id="a.py#f"),
    ]
    assert build_sources(chunks) == ["a.py#f", "b.py"]


def test_seed_chunks_stay_ahead_of_expanded():
    # prepare_chunks_for_agent emits seed docs before expanded docs;
    # build_sources must not reorder them
    chunks = [
        chunk("seed-uuid", canonical_id="seed.py#hit"),
        chunk("expanded-uuid", canonical_id="expanded.py#neighbor"),
    ]
    assert build_sources(chunks) == ["seed.py#hit", "expanded.py#neighbor"]


def test_missing_metadata_dict_is_tolerated():
    assert build_sources([{"document_id": "uuid-9", "metadata": None}]) == ["uuid-9"]


def test_empty_input():
    assert build_sources([]) == []
