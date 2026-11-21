# ingestion_service/tests/codebase/test_reuse_range_entries.py
"""
Issue #416, WP4 (specs/015-per-window-source-ranges section 4): for an artifact
that is reused (not re-chunked, not re-embedded), ingestion recomputes its
windows under the unchanged chunking config and sends each window's verified
range with the SHA-256 of the window text, so the vector store can patch the
stored passage only when it is exactly that window.

The entries must be exactly what the embed path would have written for the same
node, must never need an embedder, and must not change anything about the node.
"""

import hashlib
from types import SimpleNamespace
from uuid import uuid4

import pytest

from shared.chunkers.text import TextChunker
from src.api.v1.codebase_ingest import (
    _chunk_and_buffer_node,
    _reuse_range_entries,
)
from src.core.codebase.repo_graph_builder import RepoGraphBuilder
from src.core.pipeline import IngestionPipeline

pytestmark = pytest.mark.unit

UNVERIFIED = "artifact range not verified"

BLOCK = "".join(f"    total += compute({i}) * weight  # step {i}\n" for i in range(5))
SOURCE = (
    "import os\n\n\n"
    "def first(weight):\n    total = 0\n" + BLOCK * 3 + "    return total\n\n\n"
    "def second(x):\n    return x + 1\n"
)


def sha(text):
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def pipeline(chunk_size=90, overlap=30):
    chunker = TextChunker(
        chunk_size=chunk_size, overlap=overlap, chunk_strategy="line_window"
    )
    holder = SimpleNamespace(_chunker=chunker)
    holder._chunk = lambda text, source_type, provider: IngestionPipeline._chunk(
        holder, text, source_type, provider
    )
    # No _embed, no _vector_store: computing reuse entries must not need them.
    return holder


class Buffer:
    def __init__(self):
        self.chunks = []

    def append(self, chunk, document_id, ordinal):
        self.chunks.append((ordinal, chunk))


def node_for(tmp_path, name):
    (tmp_path / "m.py").write_text(SOURCE, encoding="utf-8", newline="")
    graph = RepoGraphBuilder(tmp_path, ingestion_id=str(uuid4())).build()
    entity = next(
        e for e in graph.all_entities()
        if e.get("name") == name and e.get("text")
    )
    return SimpleNamespace(
        text=entity["text"],
        relative_path=entity["relative_path"],
        doc_type=entity["doc_type"],
        canonical_id=entity["canonical_id"],
        document_id=str(uuid4()),
        start_line=entity["start_line"],
        end_line=entity["end_line"],
    )


def test_entries_equal_what_the_embed_path_writes_for_the_same_node(tmp_path):
    node = node_for(tmp_path, "first")
    pipe = pipeline()
    buffer = Buffer()
    _chunk_and_buffer_node(pipe, buffer, node, "repo", "ollama")
    written = buffer.chunks  # (ordinal, chunk) as the vector store would get them

    entries = _reuse_range_entries(pipe, node, "ollama")

    assert len(entries) == len(written) > 3
    for entry, (ordinal, chunk) in zip(entries, written):
        assert entry["chunk_index"] == ordinal
        assert entry["text_sha256"] == sha(chunk.content)
        assert entry["start_line"] == chunk.metadata.get("start_line")
        assert entry["end_line"] == chunk.metadata.get("end_line")
        assert entry["range_reason"] == chunk.metadata.get("range_reason")


def test_a_verified_artifact_yields_ranges_and_no_reasons(tmp_path):
    entries = _reuse_range_entries(pipeline(), node_for(tmp_path, "first"), "ollama")
    assert all(
        e["start_line"] is not None and e["range_reason"] is None for e in entries
    )
    assert [e["chunk_index"] for e in entries] == list(range(len(entries)))


def test_an_unverified_artifact_yields_the_reason_for_every_window(tmp_path):
    node = node_for(tmp_path, "first")
    node.start_line = node.end_line = None
    entries = _reuse_range_entries(pipeline(), node, "ollama")
    assert len(entries) > 3
    assert all(
        e["start_line"] is None and e["end_line"] is None
        and e["range_reason"] == UNVERIFIED
        for e in entries
    )
    assert all(len(e["text_sha256"]) == 64 for e in entries)


def test_repeated_windows_are_still_distinct_entries(tmp_path):
    node = node_for(tmp_path, "first")
    pipe = pipeline(chunk_size=len(BLOCK), overlap=0)
    entries = _reuse_range_entries(pipe, node, "x")
    digests = [e["text_sha256"] for e in entries]
    assert len(set(digests)) < len(digests)  # the same block appears three times
    assert len({(e["start_line"], e["end_line"]) for e in entries}) == len(entries)


def test_computing_entries_changes_nothing_about_the_node(tmp_path):
    node = node_for(tmp_path, "first")
    before = dict(vars(node))
    _reuse_range_entries(pipeline(), node, "ollama")
    assert vars(node) == before


def test_an_artifact_without_text_has_no_entries():
    node = SimpleNamespace(text="", start_line=None, end_line=None)
    assert _reuse_range_entries(pipeline(), node, "ollama") == []
