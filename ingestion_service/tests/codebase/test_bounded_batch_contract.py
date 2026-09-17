"""#160: split artifacts preserve ordinals; invalid batches never write."""

from unittest.mock import Mock

import pytest

from shared.chunks import Chunk
from src.core.http_vectorstore import HttpVectorStore
from src.core.pipeline import IngestionPipeline
from src.core.codebase.embedding_buffer import EmbeddingBuffer
from src.core.config import Settings
from shared.embedders.ollama import OllamaEmbedder
import requests


pytestmark = pytest.mark.unit


@pytest.mark.parametrize(
    "setting",
    [
        "INGESTION_NODE_PAGE_SIZE",
        "INGESTION_EMBED_BATCH_SIZE",
        "INGESTION_EMBED_MAX_BYTES",
        "INGESTION_MAX_ARTIFACT_BYTES",
    ],
)
@pytest.mark.parametrize("value", [0, -1])
def test_memory_limits_are_positive(setting, value):
    with pytest.raises(ValueError):
        Settings(_env_file=None, DATABASE_URL="unused", **{setting: value})


def test_ollama_timeout_is_finite_and_propagates(monkeypatch):
    def fail(url, *, json, timeout):
        assert timeout == (10, 120)
        raise requests.Timeout("fixture deadline")

    monkeypatch.setattr("shared.embedders.ollama.requests.post", fail)
    with pytest.raises(RuntimeError, match="fixture deadline"):
        OllamaEmbedder("http://unused", "fixture").embed(chunks(1))


def chunks(count):
    return [Chunk(chunk_id=f"c{i}", content=f"text {i}") for i in range(count)]


def test_explicit_ordinals_survive_separate_pipeline_calls():
    store = HttpVectorStore("http://unused")
    records = []
    store.add_vectors = lambda batch: records.extend(batch)
    embedder = Mock()
    embedder.embed.side_effect = lambda items: [[float(len(c.content))] for c in items]
    pipeline = IngestionPipeline(
        validator=Mock(), embedder=embedder, vector_store=store
    )
    for indices in ([0, 1], [2, 3], [4]):
        pipeline.embed_and_persist_batch(
            chunks=chunks(len(indices)),
            ingestion_id="attempt",
            document_ids=["doc"] * len(indices),
            chunk_indices=indices,
        )
    assert [r["metadata"]["chunk_index"] for r in records] == list(range(5))
    assert all(r["metadata"]["document_id"] == "doc" for r in records)


@pytest.mark.parametrize("indices", [[0], [0, -1], [0, 1.5], [0, True], [0, 0]])
def test_bad_ordinals_fail_before_embedding_or_write(indices):
    embedder, store = Mock(), Mock()
    pipeline = IngestionPipeline(
        validator=Mock(), embedder=embedder, vector_store=store
    )
    with pytest.raises(ValueError):
        pipeline.embed_and_persist_batch(
            chunks=chunks(2),
            ingestion_id="attempt",
            document_ids=["doc", "doc"],
            chunk_indices=indices,
        )
    embedder.embed.assert_not_called()
    store.persist_batch.assert_not_called()


@pytest.mark.parametrize("embedding_count", [0, 1, 3])
def test_store_rejects_embedding_cardinality_before_http(embedding_count):
    store = HttpVectorStore("http://unused")
    store.add_vectors = Mock()
    with pytest.raises(ValueError):
        store.persist_batch(chunks(2), [[0.0]] * embedding_count, "attempt", ["a", "b"])
    store.add_vectors.assert_not_called()


@pytest.mark.parametrize("batch_size", [0, -1, True, 1.5])
def test_store_rejects_invalid_http_batch_size(batch_size):
    store = HttpVectorStore("http://unused")
    store.add_vectors = Mock()
    with pytest.raises(ValueError):
        store.persist_batch(chunks(2), [[0.0]] * 2, "attempt", ["a", "b"], batch_size)
    store.add_vectors.assert_not_called()


def test_store_preserves_explicit_ordinals_through_http_slices():
    store = HttpVectorStore("http://unused")
    batches = []
    store.add_vectors = lambda batch: batches.append(batch)
    store.persist_batch(
        chunks(4),
        [[0.0]] * 4,
        "attempt",
        ["a", "b", "a", "b"],
        batch_size=1,
        chunk_indices=[7, 0, 8, 1],
    )
    assert [r["metadata"]["chunk_index"] for b in batches for r in b] == [7, 0, 8, 1]


def test_store_rejects_duplicate_document_ordinal_before_http():
    store = HttpVectorStore("http://unused")
    store.add_vectors = Mock()
    with pytest.raises(ValueError):
        store.persist_batch(
            chunks(2),
            [[0.0]] * 2,
            "attempt",
            ["a", "a"],
            chunk_indices=[3, 3],
        )
    store.add_vectors.assert_not_called()


@pytest.mark.parametrize("buffer_size", [1, 7, 128])
def test_large_artifact_normalized_parity_across_buffers(buffer_size):
    store = HttpVectorStore("http://unused")
    records = []
    store.add_vectors = lambda batch: records.extend(batch)
    embedder = Mock()
    embedder.embed.side_effect = lambda items: [[float(len(c.content))] for c in items]
    pipeline = IngestionPipeline(
        validator=Mock(), embedder=embedder, vector_store=store
    )
    items = pipeline._chunk("x" * 128000, "code", "mock")
    assert len(items) == 143
    buffer = EmbeddingBuffer(
        pipeline, "attempt", max_chunks=buffer_size, max_bytes=7000
    )
    for index, item in enumerate(items):
        buffer.append(item, "doc", index)
        assert len(buffer.chunks) <= buffer_size
        assert buffer.byte_count <= 7000
    buffer.flush()
    assert buffer.chunks_persisted == 143
    assert not buffer.chunks and not buffer.document_ids and not buffer.chunk_indices
    assert [r["metadata"]["chunk_index"] for r in records] == list(range(143))
    assert [r["metadata"]["chunk_text"] for r in records] == [c.content for c in items]
    assert [r["vector"] for r in records] == [[float(len(c.content))] for c in items]
    assert [r["metadata"]["source_metadata"] for r in records] == [
        {**c.metadata, "chunk_text": c.content} for c in items
    ]


def test_buffer_bounds_utf8_not_characters_and_rejects_oversize():
    pipeline = Mock()
    buffer = EmbeddingBuffer(pipeline, "attempt", max_chunks=128, max_bytes=8)
    buffer.append(Chunk(chunk_id="a", content="雪雪"), "doc", 0)
    buffer.append(Chunk(chunk_id="b", content="雪"), "doc", 1)
    assert buffer.chunks_persisted == 1
    assert buffer.byte_count == 3
    with pytest.raises(ValueError, match="9 UTF-8 bytes"):
        buffer.append(Chunk(chunk_id="c", content="雪雪雪"), "doc", 2)
    assert buffer.byte_count == 3
    assert buffer.max_buffer_bytes == 6


def test_buffer_failure_never_acknowledges_or_accepts_successor():
    pipeline = Mock()
    pipeline.embed_and_persist_batch.side_effect = RuntimeError("write failed")
    callback = Mock()
    buffer = EmbeddingBuffer(
        pipeline,
        "attempt",
        max_chunks=1,
        max_bytes=100,
        on_flush=callback,
    )
    first = Chunk(chunk_id="a", content="first")
    buffer.append(first, "doc", 0)
    with pytest.raises(RuntimeError, match="write failed"):
        buffer.append(Chunk(chunk_id="b", content="second"), "doc", 1)
    assert buffer.chunks == [first]
    assert buffer.chunks_persisted == 0
    callback.assert_not_called()


def test_empty_buffer_never_embeds():
    pipeline = Mock()
    buffer = EmbeddingBuffer(pipeline, "attempt", max_chunks=1, max_bytes=1)
    buffer.flush()
    pipeline.embed_and_persist_batch.assert_not_called()
    assert (
        buffer.chunks_persisted
        == buffer.max_buffer_chunks
        == buffer.max_buffer_bytes
        == 0
    )
