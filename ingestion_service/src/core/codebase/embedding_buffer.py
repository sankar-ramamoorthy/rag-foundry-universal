"""Count- and UTF-8-byte-bounded embedding buffer for repository ingestion."""

from collections.abc import Callable

from shared.chunks import Chunk
from src.core.pipeline import IngestionPipeline


class EmbeddingBuffer:
    """Flush synchronously before accepting a successor beyond either limit.

    The caller owns artifact chunking and the supported artifact envelope.
    Successful flushes mean acknowledged writes, not resumable checkpoints.
    On any failure the caller must abandon this buffer and fail the attempt.
    """

    def __init__(
        self,
        pipeline: IngestionPipeline,
        ingestion_id: str,
        *,
        max_chunks: int,
        max_bytes: int,
        on_flush: Callable[[], None] | None = None,
    ):
        if any(
            type(limit) is not int or limit <= 0 for limit in (max_chunks, max_bytes)
        ):
            raise ValueError("Embedding buffer limits must be positive integers")
        self.pipeline = pipeline
        self.ingestion_id = ingestion_id
        self.max_chunks = max_chunks
        self.max_bytes = max_bytes
        self.on_flush = on_flush
        self.chunks: list[Chunk] = []
        self.document_ids: list[str] = []
        self.chunk_indices: list[int] = []
        self.byte_count = 0
        self.chunks_persisted = 0
        self.max_buffer_chunks = 0
        self.max_buffer_bytes = 0

    def append(self, chunk: Chunk, document_id: str, chunk_index: int) -> None:
        size = len(chunk.content.encode("utf-8"))
        if size > self.max_bytes:
            raise ValueError(
                f"Chunk {document_id}/{chunk_index} is {size} UTF-8 bytes; "
                f"buffer limit is {self.max_bytes}"
            )
        if self.chunks and (
            len(self.chunks) >= self.max_chunks
            or self.byte_count + size > self.max_bytes
        ):
            self.flush()
        self.chunks.append(chunk)
        self.document_ids.append(document_id)
        self.chunk_indices.append(chunk_index)
        self.byte_count += size
        self.max_buffer_chunks = max(self.max_buffer_chunks, len(self.chunks))
        self.max_buffer_bytes = max(self.max_buffer_bytes, self.byte_count)

    def flush(self) -> None:
        if not self.chunks:
            return
        self.pipeline.embed_and_persist_batch(
            chunks=self.chunks,
            ingestion_id=self.ingestion_id,
            document_ids=self.document_ids,
            chunk_indices=self.chunk_indices,
        )
        self.chunks_persisted += len(self.chunks)
        self.chunks.clear()
        self.document_ids.clear()
        self.chunk_indices.clear()
        self.byte_count = 0
        if self.on_flush:
            self.on_flush()
