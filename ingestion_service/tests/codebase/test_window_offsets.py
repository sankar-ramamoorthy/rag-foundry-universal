# ingestion_service/tests/codebase/test_window_offsets.py
"""
Issue #416, WP1 (specs/015-per-window-source-ranges): the line-window chunker
reports where each window starts, without changing a single window.

The reference below is the pre-change `line_windows` algorithm copied verbatim.
The new `line_windows` must equal it on every input, so passage text,
boundaries, count and order (and therefore embeddings and the chunking version)
are unchanged by construction.
"""

import random
from typing import List

import pytest

from shared.chunkers.selector import ChunkerFactory
from shared.chunkers.text import (
    TextChunker,
    _Packer,
    _split_line,
    line_window_offsets,
    line_windows,
)

pytestmark = pytest.mark.unit


def reference_line_windows(
    text: str, max_chars: int, overlap: int, max_tokens: int | None = None
) -> List[str]:
    """The pre-#416 implementation, unchanged."""
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


ALPHABET = [
    "a", "b", "x", " ", "\t", "\n", "\r\n", "\r", "é", "日", "😀", "_", "=", "(",
]


def generated(seed: int) -> str:
    rng = random.Random(seed)
    return "".join(rng.choice(ALPHABET) for _ in range(rng.randint(0, 600)))


SETTINGS = [(40, 0), (40, 15), (97, 30)]
CASES = [(seed, mc, ov) for seed in range(60) for mc, ov in SETTINGS]


@pytest.mark.parametrize("seed,max_chars,overlap", CASES)
def test_line_windows_unchanged_and_offsets_exact(seed, max_chars, overlap):
    text = generated(seed)
    new = line_windows(text, max_chars, overlap)
    assert new == reference_line_windows(text, max_chars, overlap)
    pairs = line_window_offsets(text, max_chars, overlap)
    assert [w for w, _ in pairs] == new
    for window, offset in pairs:
        assert type(offset) is int and offset >= 0
        assert text[offset : offset + len(window)] == window


@pytest.mark.parametrize("seed", range(20))
def test_token_budget_path_is_unchanged_too(seed):
    text = generated(seed + 1000)
    assert line_windows(text, 80, 20, 12) == reference_line_windows(text, 80, 20, 12)
    for window, offset in line_window_offsets(text, 80, 20, 12):
        assert text[offset : offset + len(window)] == window


def test_empty_text_has_no_windows():
    assert line_window_offsets("", 40, 10) == []
    assert line_windows("", 40, 10) == []


def test_offsets_are_nondecreasing_and_the_first_window_starts_at_zero():
    text = "".join(f"line {i}\n" for i in range(50))
    offsets = [o for _, o in line_window_offsets(text, 60, 20)]
    assert offsets[0] == 0
    assert offsets == sorted(offsets) and len(set(offsets)) == len(offsets)


def test_overlapping_windows_share_text_and_keep_their_own_offsets():
    text = "".join(f"row{i:02d}\n" for i in range(40))
    pairs = line_window_offsets(text, 40, 16)
    assert len(pairs) > 2
    overlapped = 0
    for (first, a), (second, b) in zip(pairs, pairs[1:]):
        assert b > a  # strictly later start
        if b < a + len(first):
            overlapped += 1
            shared = text[b : a + len(first)]
            assert first.endswith(shared) and second.startswith(shared)
    assert overlapped >= 1


def test_repeated_text_windows_keep_distinct_exact_offsets():
    block = "".join(f"same {i}\n" for i in range(6))
    text = block * 3
    pairs = line_window_offsets(text, len(block), 0)
    # Three identical windows: the content alone cannot tell them apart.
    assert [w for w, _ in pairs] == [block, block, block]
    assert [o for _, o in pairs] == [0, len(block), 2 * len(block)]


def test_crlf_and_lone_cr_offsets_are_character_offsets():
    text = "a\r\nbb\r\nccc\rdddd\r\n" * 8
    for window, offset in line_window_offsets(text, 30, 8):
        assert text[offset : offset + len(window)] == window


def test_multibyte_offsets_are_characters_not_bytes():
    text = "".join(f"é日😀 {i}\n" for i in range(30))
    pairs = line_window_offsets(text, 40, 10)
    assert len(pairs) > 1
    for window, offset in pairs:
        assert text[offset : offset + len(window)] == window
    assert any(o != len(text[:o].encode()) for _, o in pairs)  # bytes differ


def test_a_single_long_line_split_inside_the_line_keeps_exact_offsets():
    text = "x" * 25 + " " + "y" * 60 + "\n" + "tail\n"
    pairs = line_window_offsets(text, 30, 0)
    assert len(pairs) >= 3
    for window, offset in pairs:
        assert text[offset : offset + len(window)] == window
    assert "".join(w for w, _ in pairs) == text  # contiguous, no overlap


def test_text_chunker_reports_the_offset_and_does_not_change_the_text():
    text = "".join(f"line {i}\n" for i in range(60))
    chunker = TextChunker(chunk_size=70, overlap=20, chunk_strategy="line_window")
    chunks = chunker.chunk(text)
    assert [c.content for c in chunks] == reference_line_windows(text, 70, 20)
    for chunk in chunks:
        offset = chunk.metadata["window_offset"]
        assert text[offset : offset + len(chunk.content)] == chunk.content


def test_the_chunking_config_version_is_unchanged():
    assert ChunkerFactory.VERSION == "budgeted-v2"
    chunker, params = ChunkerFactory.choose_strategy("a\nb\n", source_type="code")
    assert chunker.chunk_strategy == "line_window"
    assert set(params) == {
        "chunk_size",
        "overlap",
        "max_chars",
        "max_tokens",
    }
