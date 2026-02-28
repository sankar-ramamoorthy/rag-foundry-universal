# ingestion_service/src/core/chunkers/text.py

from __future__ import annotations
import uuid
from typing import List

from shared.chunks import Chunk
from shared.chunkers.base import BaseChunker


class TextChunker(BaseChunker):
    """Text chunker supporting multiple strategies."""

    name: str = "text_chunker"

    def __init__(
        self, chunk_size: int = 500, overlap: int = 50, chunk_strategy: str = "simple"
    ):
        self.chunk_size = chunk_size
        self.overlap = overlap
        self.chunk_strategy = chunk_strategy

    def chunk(self, content: str, **params) -> List[Chunk]:
        chunk_size = params.get("chunk_size", self.chunk_size)
        overlap = params.get("overlap", self.overlap)
        chunk_strategy = params.get("chunk_strategy", self.chunk_strategy)

        if chunk_strategy == "simple":
            return self._chunk_simple(content, chunk_size, overlap)
        elif chunk_strategy == "sentence":
            return self._chunk_by_sentence(content, chunk_size, overlap)
        elif chunk_strategy == "paragraph":
            return self._chunk_by_paragraph(content, chunk_size, overlap)
        else:
            raise ValueError(f"Unknown text chunk strategy: {chunk_strategy}")

    def _chunk_simple(self, text: str, chunk_size: int, overlap: int) -> List[Chunk]:
        chunks: List[Chunk] = []
        start = 0
        text_length = len(text)

        while start < text_length:
            end = min(start + chunk_size, text_length)
            chunk_text = text[start:end]
            chunks.append(
                Chunk(content=chunk_text, chunk_id=str(uuid.uuid4()), metadata={})
            )
            start += chunk_size - overlap

        return chunks

    def _chunk_by_sentence(
        self, text: str, chunk_size: int, overlap: int
    ) -> List[Chunk]:
        import re

        sentences = re.split(r"(?<=[.!?])\s+", text)
        chunks: List[Chunk] = []
        buffer = ""

        for sentence in sentences:
            if len(buffer) + len(sentence) > chunk_size:
                if buffer:
                    chunks.append(
                        Chunk(content=buffer, chunk_id=str(uuid.uuid4()), metadata={})
                    )
                buffer = sentence
            else:
                buffer += (" " if buffer else "") + sentence

        if buffer:
            chunks.append(
                Chunk(content=buffer, chunk_id=str(uuid.uuid4()), metadata={})
            )

        return chunks

    def _chunk_by_paragraph(
        self, text: str, chunk_size: int, overlap: int
    ) -> List[Chunk]:
        """
        Splits text into chunks by paragraphs, merging consecutive paragraphs until
        the buffer exceeds `chunk_size`.  

        - Paragraphs are defined as blocks separated by two newlines (\n\n).  
        - Paragraphs are merged together until the combined length exceeds `chunk_size`.  
        - If a paragraph is larger than `chunk_size`, it will be a chunk by itself.  
        - `overlap` is currently not used in paragraph strategy.  

        Args:
            text (str): Text to chunk.
            chunk_size (int): Maximum size of a chunk before creating a new one.
            overlap (int): Overlap between chunks (ignored in paragraph strategy).

        Returns:
            List[Chunk]: List of Chunk objects containing paragraph(s).
        """

        paragraphs = text.split("\n\n")
        chunks: List[Chunk] = []
        buffer = ""

        for para in paragraphs:
            para = para.strip()
            if not para:
                continue

            if len(buffer) + len(para) > chunk_size:
                if buffer:
                    chunks.append(
                        Chunk(content=buffer, chunk_id=str(uuid.uuid4()), metadata={})
                    )
                buffer = para
            else:
                buffer += ("\n\n" if buffer else "") + para

        if buffer:
            chunks.append(
                Chunk(content=buffer, chunk_id=str(uuid.uuid4()), metadata={})
            )

        return chunks
