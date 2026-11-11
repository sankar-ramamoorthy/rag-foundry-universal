# src/ingestion_service/core/chunkers/text.py

from __future__ import annotations
import re
import uuid
from typing import List

from shared.chunks import Chunk
from shared.chunkers.base import BaseChunker


_TOKEN_RUN = re.compile(r"[A-Za-z0-9]+|[^\sA-Za-z0-9]")


def estimate_tokens(text: str) -> int:
    """Conservative, model-agnostic estimate of subword tokens in ``text``.

    Each punctuation/symbol and each non-ASCII character counts as one token
    (BERT-style tokenizers split them individually; CJK text is roughly one
    token per character) and an ASCII alphanumeric run of length L counts as
    ceil(L / 3). Calibrated in the CI-06 investigation against the
    mxbai-embed-large WordPiece vocabulary: on two development corpora it
    overestimates in aggregate by about a third. It is additive across lines.
    """
    total = 0
    for run in _TOKEN_RUN.findall(text):
        if run[0].isascii() and run[0].isalnum():
            total += -(-len(run) // 3)
        else:
            total += 1
    return total


def _split_line(line: str, max_chars: int, max_tokens: int | None) -> List[str]:
    """Split one line into consecutive pieces that fit both budgets."""
    pieces: List[str] = []
    while line:
        end = min(len(line), max_chars)
        if max_tokens is not None:
            while end > 1 and estimate_tokens(line[:end]) > max_tokens:
                # Shrink proportionally, then by one, so progress is bounded.
                ratio = max_tokens / estimate_tokens(line[:end])
                end = min(end - 1, max(1, int(end * ratio)))
        if end < len(line):
            # Prefer ending after whitespace so words stay whole.
            space = max(line.rfind(" ", 0, end), line.rfind("\t", 0, end))
            if space >= end // 2:
                end = space + 1
        pieces.append(line[:end])
        line = line[end:]
    return pieces


def line_windows(
    text: str, max_chars: int, overlap: int, max_tokens: int | None = None
) -> List[str]:
    """Split text into exact, contiguous windows that fit an embedding input.

    CI-06 (#337): every window is a verbatim substring of ``text`` and the
    windows together cover all of it, so a stored passage can be the exact
    embedding input. A window holds at most ``max_chars`` characters and, if
    given, at most ``max_tokens`` by :func:`estimate_tokens`. Windows end on
    line boundaries; a line that alone exceeds a budget is split inside the
    line. Each window after the first repeats up to ``overlap`` characters of
    whole trailing lines from its predecessor.
    """
    if type(max_chars) is not int or max_chars <= 0:
        raise ValueError("max_chars must be a positive integer")
    if type(overlap) is not int or not 0 <= overlap < max_chars:
        raise ValueError("overlap must be an integer in [0, max_chars)")
    if max_tokens is not None and (type(max_tokens) is not int or max_tokens <= 0):
        raise ValueError("max_tokens must be a positive integer")

    pieces: List[str] = []
    for line in text.splitlines(keepends=True):
        pieces.extend(_split_line(line, max_chars, max_tokens))
    packer = _Packer(pieces, max_chars, max_tokens)

    windows: List[str] = []
    start = 0
    while start < len(pieces):
        end = packer.window_end(start)
        windows.append("".join(pieces[start:end]))
        if end == len(pieces):
            break
        start = packer.overlap_start(start, end, overlap)
    return windows


class _Packer:
    """Greedy packing of whole pieces under character and token budgets."""

    def __init__(self, pieces: List[str], max_chars: int, max_tokens: int | None):
        self.pieces = pieces
        self.max_chars = max_chars
        self.token_cap = max_tokens if max_tokens is not None else 0
        self.costs = [
            estimate_tokens(p) if max_tokens is not None else 0 for p in pieces
        ]

    def fits(self, chars: int, tokens: int) -> bool:
        return chars <= self.max_chars and tokens <= self.token_cap

    def window_end(self, start: int) -> int:
        end, chars, tokens = start, 0, 0
        while end < len(self.pieces) and self.fits(
            chars + len(self.pieces[end]), tokens + self.costs[end]
        ):
            chars += len(self.pieces[end])
            tokens += self.costs[end]
            end += 1
        return end

    def overlap_start(self, start: int, end: int, overlap: int) -> int:
        """Back up over whole trailing pieces for overlap, but leave room for
        the next unseen piece so every window makes progress."""
        begin, carried, carried_tokens = end, 0, 0
        while begin - 1 > start:
            prev = begin - 1
            chars = carried + len(self.pieces[prev])
            tokens = carried_tokens + self.costs[prev]
            if chars > overlap or not self.fits(
                chars + len(self.pieces[end]), tokens + self.costs[end]
            ):
                break
            begin, carried, carried_tokens = prev, chars, tokens
        return begin


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

        max_chars = params.get("max_chars")
        max_tokens = params.get("max_tokens")

        if chunk_strategy == "line_window":
            return [
                Chunk(content=text, chunk_id=str(uuid.uuid4()), metadata={})
                for text in line_windows(content, chunk_size, overlap, max_tokens)
            ]
        if chunk_strategy == "simple":
            if max_chars is not None and chunk_size > max_chars:
                raise ValueError("chunk_size must not exceed max_chars")
            chunks = self._chunk_simple(content, chunk_size, overlap)
        elif chunk_strategy == "sentence":
            chunks = self._chunk_by_sentence(content, chunk_size, overlap)
        elif chunk_strategy == "paragraph":
            chunks = self._chunk_by_paragraph(content, chunk_size, overlap)
        else:
            raise ValueError(f"Unknown text chunk strategy: {chunk_strategy}")
        if max_chars is None:
            return chunks
        return self._fit(chunks, max_chars, max_tokens)

    @staticmethod
    def _fit(
        chunks: List[Chunk], max_chars: int, max_tokens: int | None
    ) -> List[Chunk]:
        """CI-06 (#337): split any unit that would not fit one embedding input.

        Sentence/paragraph units are unbounded (one "sentence" of code can be
        thousands of characters); without this the embedder had to drop text.
        """
        fitted: List[Chunk] = []
        for chunk in chunks:
            text = chunk.content
            if len(text) <= max_chars and (
                max_tokens is None or estimate_tokens(text) <= max_tokens
            ):
                fitted.append(chunk)
                continue
            fitted.extend(
                Chunk(content=part, chunk_id=str(uuid.uuid4()), metadata={})
                for part in line_windows(text, max_chars, 0, max_tokens)
            )
        return fitted

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
