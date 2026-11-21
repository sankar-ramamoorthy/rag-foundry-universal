# ingestion_service/tests/codebase/test_window_ranges.py
"""
Issue #416, WP2 (specs/015-per-window-source-ranges): every passage window
gets a verified source line range from the chunker's own offset, or an explicit
reason. Nothing about the passages changes: text, order, count and chunking
version stay as they were.

"Resolves" is checked the way a consumer would: read the lines (LF-only
convention) from the stored module text and require that they contain the window
exactly, where the window may start after some text on its first line and end
before some text on its last line.
"""

from types import SimpleNamespace
from uuid import uuid4

import pytest

from shared.chunkers.text import TextChunker, split_for_overflow
from src.api.v1.codebase_ingest import _chunk_and_buffer_node, _passage_spans
from src.core.codebase.repo_graph_builder import RepoGraphBuilder
from src.core.codebase.source_span import (
    NewlineIndex,
    piece_ranges,
    split_lines,
    window_range,
)
from src.core.pipeline import IngestionPipeline

pytestmark = pytest.mark.unit

UNVERIFIED = "artifact range not verified"
NO_OFFSET = "window offset not reported"
MISMATCH = "passage does not match artifact text at reported offset"


def resolves(file_text: str, start: int, end: int, content: str) -> bool:
    lines = split_lines(file_text)
    region = lines[start - 1 : end]
    joined = "".join(region)
    first, last = len(region[0]), len(region[-1])
    i = joined.find(content)
    while i != -1:
        if i < first and i + len(content) > len(joined) - last:
            return True
        i = joined.find(content, i + 1)
    return False


def small_pipeline(chunk_size=120, overlap=40):
    chunker = TextChunker(
        chunk_size=chunk_size, overlap=overlap, chunk_strategy="line_window"
    )
    holder = SimpleNamespace(_chunker=chunker)
    holder._chunk = lambda text, source_type, provider: IngestionPipeline._chunk(
        holder, text, source_type, provider
    )
    return holder


class Buffer:
    def __init__(self):
        self.items = []

    def append(self, chunk, document_id, ordinal):
        self.items.append((chunk, document_id, ordinal))


def entities_for(tmp_path, name, source):
    (tmp_path / name).write_text(source, encoding="utf-8", newline="")
    graph = RepoGraphBuilder(tmp_path, ingestion_id=str(uuid4())).build()
    return [e for e in graph.all_entities() if e.get("relative_path") == name]


def node_from(entity):
    return SimpleNamespace(
        text=entity["text"],
        relative_path=entity["relative_path"],
        doc_type=entity["doc_type"],
        canonical_id=entity["canonical_id"],
        document_id=str(uuid4()),
        start_line=entity["start_line"],
        end_line=entity["end_line"],
    )


def tag(pipeline, node):
    buffer = Buffer()
    _chunk_and_buffer_node(pipeline, buffer, node, "repo", "ollama")
    return [c for c, _, _ in buffer.items], buffer


# --- window_range ---

TEXT = "".join(f"line {i:02d}\n" for i in range(12))


def test_newline_index_counts_newlines_before_a_position():
    index = NewlineIndex("ab\ncd\n\nef")
    positions = (0, 2, 3, 5, 6, 7, 9)
    assert [index.lines_before(p) for p in positions] == [0, 0, 1, 1, 2, 3, 3]


def test_window_range_maps_offset_to_lines_from_the_artifact_start():
    # Windows of two lines each (8 chars per line), artifact starting at line 100.
    assert window_range(TEXT, 100, 0, TEXT[:16]) == (100, 101)
    assert window_range(TEXT, 100, 16, TEXT[16:32]) == (102, 103)
    assert window_range(TEXT, 100, 8, TEXT[8:24]) == (101, 102)  # overlap


def test_window_range_handles_a_window_inside_a_long_line():
    text = "short\n" + "x" * 50 + "\nend\n"
    # A window that starts and ends inside the second line names that line.
    assert window_range(text, 10, 6 + 5, text[11:30]) == (11, 11)


def test_window_range_rejects_anything_it_cannot_verify():
    assert window_range(TEXT, 1, 0, "") is None
    assert window_range(TEXT, 1, 1, TEXT[:16]) is None  # wrong offset
    assert window_range(TEXT, 1, -1, TEXT[:16]) is None
    assert window_range(TEXT, 1, len(TEXT), "x") is None  # past the end
    assert window_range(TEXT, 1, 0, TEXT + "extra") is None  # longer than the text
    assert window_range(TEXT, 0, 0, TEXT[:8]) is None  # no valid artifact start


# --- _passage_spans: reasons and bookkeeping ---


def chunks_of(text, **kw):
    pipe = small_pipeline(**kw)
    return pipe._chunk(text, "code", "ollama")


def test_every_window_is_tagged_and_the_transient_offset_is_removed():
    node = SimpleNamespace(start_line=5, end_line=5 + TEXT.count("\n") - 1, text=TEXT)
    chunks = chunks_of(TEXT, chunk_size=40, overlap=16)
    assert len(chunks) > 2
    spans = _passage_spans(node, chunks)
    assert len(spans) == len(chunks)
    assert all("window_offset" not in c.metadata for c in chunks)
    assert all(s["start_line"] <= s["end_line"] for s in spans)
    assert spans[0]["start_line"] == 5
    assert spans[-1]["end_line"] == node.end_line


def test_unverified_artifact_gives_every_window_the_unverified_reason():
    node = SimpleNamespace(start_line=None, end_line=None, text=TEXT)
    chunks = chunks_of(TEXT, chunk_size=40, overlap=16)
    spans = _passage_spans(node, chunks)
    assert spans == [{"range_reason": UNVERIFIED}] * len(chunks)
    assert all("window_offset" not in c.metadata for c in chunks)


@pytest.mark.parametrize("bad", [(0, 3), (5, 2), ("1", 4), (True, 4)])
def test_malformed_artifact_range_is_treated_as_unverified(bad):
    node = SimpleNamespace(start_line=bad[0], end_line=bad[1], text=TEXT)
    spans = _passage_spans(node, chunks_of(TEXT, chunk_size=40, overlap=16))
    assert all(s == {"range_reason": UNVERIFIED} for s in spans)


def test_a_chunker_without_offsets_gives_the_no_offset_reason():
    node = SimpleNamespace(start_line=1, end_line=12, text=TEXT)
    chunks = chunks_of(TEXT, chunk_size=40, overlap=16)
    for c in chunks:
        c.metadata.pop("window_offset")
    assert all(s == {"range_reason": NO_OFFSET} for s in _passage_spans(node, chunks))


def test_a_corrupted_offset_gives_the_mismatch_reason_never_a_wrong_range():
    node = SimpleNamespace(start_line=1, end_line=12, text=TEXT)
    chunks = chunks_of(TEXT, chunk_size=40, overlap=16)
    chunks[1].metadata["window_offset"] += 1
    spans = _passage_spans(node, chunks)
    assert spans[1] == {"range_reason": MISMATCH}
    assert "start_line" in spans[0] and "start_line" in spans[2]


def test_a_window_that_does_not_belong_to_the_artifact_text_is_a_mismatch():
    node = SimpleNamespace(start_line=1, end_line=12, text=TEXT)
    chunks = chunks_of("something else entirely\n" * 5, chunk_size=40, overlap=0)
    assert all(s == {"range_reason": MISMATCH} for s in _passage_spans(node, chunks))


# --- through the real extractor, assembler and ingestion tagging ---

BLOCK = "".join(f"    total += compute({i}) * weight  # step {i}\n" for i in range(5))
SOURCE = (
    "import os\n\n\n"
    "def first(weight):\n    total = 0\n" + BLOCK * 3 + "    return total\n\n\n"
    "def second(x):\n    return x + 1\n"
)


def check_all_windows_resolve(tmp_path, name, source, **chunker):
    entities = entities_for(tmp_path, name, source)
    module = next(e for e in entities if e["artifact_type"] == "MODULE")
    module_text = module["text"]
    seen = 0
    for entity in entities:
        if not entity.get("text") or entity.get("start_line") is None:
            continue
        pipe = small_pipeline(**chunker)
        chunks, _ = tag(pipe, node_from(entity))
        for chunk in chunks:
            md = chunk.metadata
            assert "window_offset" not in md
            assert md["start_line"] >= entity["start_line"]
            assert md["end_line"] <= entity["end_line"]
            assert resolves(
                module_text, md["start_line"], md["end_line"], chunk.content
            )
            seen += 1
    return entities, seen


def test_python_windows_resolve_against_the_stored_module_text(tmp_path):
    _, seen = check_all_windows_resolve(
        tmp_path, "m.py", SOURCE, chunk_size=90, overlap=30
    )
    assert seen > 6


def test_repeated_text_every_window_gets_its_own_correct_range(tmp_path):
    entities = entities_for(tmp_path, "r.py", SOURCE)
    first = next(e for e in entities if e["name"] == "first")
    module_text = next(e for e in entities if e["artifact_type"] == "MODULE")["text"]
    pipe = small_pipeline(chunk_size=len(BLOCK), overlap=0)
    chunks, _ = tag(pipe, node_from(first))
    ranges = [(c.metadata["start_line"], c.metadata["end_line"]) for c in chunks]
    # The same block appears three times, so some windows have identical text.
    contents = [c.content for c in chunks]
    assert len(set(contents)) < len(contents)
    # Yet no two windows share a range, and each is correct for its position.
    assert len(set(ranges)) == len(ranges)
    assert ranges == sorted(ranges)
    for chunk in chunks:
        md = chunk.metadata
        assert resolves(module_text, md["start_line"], md["end_line"], chunk.content)
    # A copy's range must be the lines of that copy, not an earlier copy.
    block_lines = BLOCK.count("\n")
    assert (ranges[2][0] - ranges[1][0]) == block_lines == (ranges[3][0] - ranges[2][0])


def test_overlapping_windows_have_overlapping_ranges_that_each_resolve(tmp_path):
    entities = entities_for(tmp_path, "o.py", SOURCE)
    first = next(e for e in entities if e["name"] == "first")
    module_text = next(e for e in entities if e["artifact_type"] == "MODULE")["text"]
    chunks, _ = tag(small_pipeline(chunk_size=200, overlap=90), node_from(first))
    ranges = [(c.metadata["start_line"], c.metadata["end_line"]) for c in chunks]
    assert len(ranges) > 2
    assert any(b[0] <= a[1] for a, b in zip(ranges, ranges[1:]))
    for chunk, (s, e) in zip(chunks, ranges):
        assert resolves(module_text, s, e, chunk.content)


def test_a_single_window_artifact_keeps_exactly_the_artifact_range(tmp_path):
    entities = entities_for(tmp_path, "s.py", SOURCE)
    second = next(e for e in entities if e["name"] == "second")
    chunks, _ = tag(small_pipeline(chunk_size=4000, overlap=100), node_from(second))
    assert len(chunks) == 1
    assert (chunks[0].metadata["start_line"], chunks[0].metadata["end_line"]) == (
        second["start_line"],
        second["end_line"],
    )


def test_crlf_and_lone_cr_sources_resolve_against_the_stored_text(tmp_path):
    for sep in ("\r\n", "\r"):
        sub = tmp_path / ("crlf" if sep == "\r\n" else "cr")
        sub.mkdir()
        _, seen = check_all_windows_resolve(
            sub, "c.py", SOURCE.replace("\n", sep), chunk_size=90, overlap=30
        )
        assert seen > 0


def test_multibyte_sources_resolve(tmp_path):
    body = "".join(f'    s{i} = "é日😀 {i}"\n' for i in range(40))
    source = "def f():\n" + body + "    return 1\n"
    _, seen = check_all_windows_resolve(
        tmp_path, "u.py", source, chunk_size=70, overlap=20
    )
    assert seen > 3


def test_a_long_line_split_inside_the_line_names_that_line(tmp_path):
    long_line = "    value = [" + ", ".join(str(i) for i in range(200)) + "]\n"
    source = "def f():\n" + long_line + "    return value\n"
    _, seen = check_all_windows_resolve(
        tmp_path, "l.py", source, chunk_size=60, overlap=0
    )
    assert seen > 4


# --- nothing else about the passages changes ---


def test_passage_text_order_and_count_are_exactly_the_chunkers(tmp_path):
    entities = entities_for(tmp_path, "p.py", SOURCE)
    first = next(e for e in entities if e["name"] == "first")
    pipe = small_pipeline(chunk_size=90, overlap=30)
    direct = [c.content for c in pipe._chunk(first["text"], "code", "ollama")]
    chunks, buffer = tag(pipe, node_from(first))
    assert [c.content for c in chunks] == direct
    assert [o for _, _, o in buffer.items] == list(range(len(direct)))


def test_unverified_node_still_buffers_every_passage_with_a_reason():
    node = SimpleNamespace(
        text=TEXT,
        relative_path="x.py",
        doc_type="python source",
        canonical_id="x.py",
        document_id=str(uuid4()),
        start_line=None,
        end_line=None,
    )
    chunks, _ = tag(small_pipeline(chunk_size=40, overlap=16), node)
    assert len(chunks) > 2
    assert all(c.metadata["range_reason"] == UNVERIFIED for c in chunks)
    assert all("start_line" not in c.metadata for c in chunks)


# --- overflow pieces stay inside the window range and resolve ---


def test_overflow_pieces_lie_inside_the_window_range_and_resolve(tmp_path):
    entities = entities_for(tmp_path, "v.py", SOURCE)
    first = next(e for e in entities if e["name"] == "first")
    module_text = next(e for e in entities if e["artifact_type"] == "MODULE")["text"]
    chunks, _ = tag(small_pipeline(chunk_size=400, overlap=0), node_from(first))
    window = chunks[0]
    start, end = window.metadata["start_line"], window.metadata["end_line"]
    pieces = split_for_overflow(window.content)
    ranges = piece_ranges(start, window.content, pieces)
    assert all(r is not None for r in ranges)
    for piece, (s, e) in zip(pieces, ranges):
        assert start <= s <= e <= end
        assert resolves(module_text, s, e, piece)
