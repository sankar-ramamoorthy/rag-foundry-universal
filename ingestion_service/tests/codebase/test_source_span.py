# ingestion_service/tests/codebase/test_source_span.py
"""
Issue #412 / specs/014-persisted-source-spans.

Contract: every stored line range resolves to the exact source content it
claims to represent, and where that cannot be proved no range is stored.
"Resolves" is checked the way a consumer would: read the lines (LF-only
convention) and compare to the artifact text.
"""

from uuid import uuid4

import pytest

from src.core.codebase.repo_graph_builder import RepoGraphBuilder
from src.core.codebase.source_span import (
    module_range,
    piece_ranges,
    split_lines,
    verified_range,
)
from src.core.pipeline import _overflow_ranges
from shared.chunks import Chunk

pytestmark = pytest.mark.unit


def resolves(file_text: str, start: int, end: int, text: str) -> bool:
    """The consumer's check: the lines hold the text after first-line
    indentation, with only the rest of the last line allowed to follow."""
    lines = split_lines(file_text)
    region = lines[start - 1 : end]
    joined = region[0].lstrip(" \t") + "".join(region[1:])
    rest = joined[len(text) :]
    return joined.startswith(text) and rest.find("\n") in (-1, len(rest) - 1)


# --- split_lines follows the source read API convention ---


def test_split_lines_lf_only_no_phantom_line():
    assert split_lines("") == []
    assert split_lines("a\nb\n") == ["a\n", "b\n"]
    assert split_lines("a\nb") == ["a\n", "b"]
    assert split_lines("a\r\nb\n") == ["a\r\n", "b\n"]
    assert split_lines("a\rb\n") == ["a\rb\n"]  # lone CR is not a line break


# --- verified_range ---

FILE = (
    "import x\n"
    "\n"
    "def f(a):\n"
    "    return a  # trailing comment\n"
    "\n"
    "class C:\n"
    "    def m(self):\n"
    "        return 1\n"
)


def test_plain_function_range():
    lines = split_lines(FILE)
    assert verified_range(lines, 4, "def f(a):\n    return a") == (3, 4)


def test_indented_method_range_ignores_first_line_indent():
    lines = split_lines(FILE)
    assert verified_range(lines, 8, "def m(self):\n        return 1") == (7, 8)


def test_text_preceded_by_other_code_is_rejected():
    lines = ["x = 1; def f(): pass\n"]
    assert verified_range(lines, 1, "def f(): pass") is None


def test_mismatched_text_is_rejected():
    lines = split_lines(FILE)
    assert verified_range(lines, 4, "def f(b):\n    return b") is None


def test_text_that_does_not_end_on_the_claimed_line_is_rejected():
    lines = split_lines(FILE)
    assert verified_range(lines, 3, "def f(a):\n    return a") is None


def test_bad_inputs_are_none():
    lines = split_lines(FILE)
    assert verified_range(lines, None, "x") is None
    assert verified_range(lines, 99, "x") is None
    assert verified_range(lines, 1, "") is None
    assert verified_range([], 1, "x") is None


def test_module_range_is_every_line():
    assert module_range(split_lines(FILE), FILE, FILE) == (1, 8)
    assert module_range(split_lines(FILE), FILE, "other") is None


# --- through the real extractors and assembler ---

PY = (
    "import click\n"
    "\n"
    "@click.command()\n"
    "@click.option(\n"
    '    "--x",\n'
    ")\n"
    "def hello(x):\n"
    "    return x\n"
    "\n"
    "class K:\n"
    "    @staticmethod\n"
    "    def s(a):\n"
    "        return a\n"
    "\n"
    "    def t(self): return 1  # one liner\n"
)


def _entities(tmp_path, name, source):
    (tmp_path / name).write_text(source, encoding="utf-8", newline="")
    graph = RepoGraphBuilder(tmp_path, ingestion_id=str(uuid4())).build()
    return [e for e in graph.all_entities() if e.get("relative_path") == name]


def test_python_ranges_resolve_including_decorators_and_methods(tmp_path):
    entities = _entities(tmp_path, "m.py", PY)
    by_name = {e["name"]: e for e in entities if e.get("text")}
    ranged = [e for e in entities if e.get("start_line") is not None]
    assert ranged, "expected verified ranges"
    for e in ranged:
        assert resolves(PY, e["start_line"], e["end_line"], e["text"]), e["name"]
    # The decorated function's range starts at its first decorator.
    assert (by_name["hello"]["start_line"], by_name["hello"]["end_line"]) == (3, 8)
    assert (by_name["s"]["start_line"], by_name["s"]["end_line"]) == (11, 13)
    assert (by_name["t"]["start_line"], by_name["t"]["end_line"]) == (15, 15)
    module = next(e for e in entities if e["artifact_type"] == "MODULE")
    assert (module["start_line"], module["end_line"]) == (1, 15)


def _module_text(entities):
    return next(e for e in entities if e["artifact_type"] == "MODULE")["text"]


def test_crlf_file_resolves_against_the_stored_text(tmp_path):
    # The repository builder reads files with universal newlines, so the stored
    # module text (what the source read API serves) has LF line ends. Ranges
    # are relative to that stored text.
    source = PY.replace("\n", "\r\n")
    entities = _entities(tmp_path, "c.py", source)
    stored = _module_text(entities)
    ranged = [e for e in entities if e.get("start_line") is not None]
    assert ranged and "\r" not in stored
    for e in ranged:
        assert resolves(stored, e["start_line"], e["end_line"], e["text"])


def test_lone_cr_file_resolves_against_the_stored_text(tmp_path):
    source = "def f():\r    return 1\r"
    entities = _entities(tmp_path, "r.py", source)
    stored = _module_text(entities)
    for e in entities:
        if e.get("start_line") is not None:
            assert resolves(stored, e["start_line"], e["end_line"], e["text"])


TS = (
    "export class Box {\n"
    "  get(): number {\n"
    "    return 1;\n"
    "  }\n"
    "}\n"
    "\n"
    "export function open(): void {}\n"
)


def test_typescript_ranges_resolve_or_are_absent(tmp_path):
    entities = _entities(tmp_path, "box.ts", TS)
    for e in entities:
        if e.get("start_line") is not None:
            assert resolves(TS, e["start_line"], e["end_line"], e["text"]), e["name"]
        elif e.get("text"):
            assert e["end_line"] is None


# Passage-level ranges (single window, several windows, unverified artifact) are
# covered by test_window_ranges.py (issue #416), which replaced the single-passage-only
# rule of issue #412.


# --- overflow pieces never inherit the whole passage's range ---

BODY = "def big():\n" + "".join(f"    v{i} = {i}\n" for i in range(9))


def test_piece_ranges_cover_the_passage_and_resolve():
    content = BODY.rstrip("\n")
    pieces = [content[:25], content[25:60], content[60:]]
    ranges = piece_ranges(10, content, pieces)
    assert all(r is not None for r in ranges)
    assert ranges[0][0] == 10 and ranges[-1][1] == 10 + content.count("\n")
    for piece, (start, end) in zip(pieces, ranges):
        # The lines of the passage that contain the piece.
        file_text = "\n" * 9 + content + "\n"
        region = "".join(split_lines(file_text)[start - 1 : end])
        assert piece in region


def test_pieces_that_do_not_reassemble_get_no_ranges():
    assert piece_ranges(1, "abc", ["a", "x"]) == [None, None]
    assert piece_ranges(1, "abc", ["abc", ""]) == [None, None]


def test_overflow_ranges_need_a_verified_range_to_subdivide():
    chunk = Chunk(content=BODY, chunk_id="c", metadata={})
    assert _overflow_ranges(chunk, ["a", "b"]) == [None, None]
    ranged = Chunk(
        content="a\nb\nc", chunk_id="c", metadata={"start_line": 4, "end_line": 6}
    )
    assert _overflow_ranges(ranged, ["a\nb", "\nc"]) == [(4, 5), (5, 6)]


# --- persistence wiring (no database: Docker was not available) ---


def test_range_columns_are_persisted_and_refreshed_on_every_upsert():
    from shared.models.document_node import DocumentNode
    from src.core.codebase.codebase_persistence import CodebaseGraphPersistence

    columns = DocumentNode.__table__.columns
    assert columns["start_line"].nullable and columns["end_line"].nullable
    refreshed = CodebaseGraphPersistence._UPSERT_UPDATE_COLUMNS
    assert "start_line" in refreshed and "end_line" in refreshed


def test_migration_is_the_single_head_and_additive():
    import importlib.util
    from pathlib import Path

    path = (
        Path(__file__).resolve().parents[3]
        / "migrations/versions/20261121_node_source_span.py"
    )
    spec = importlib.util.spec_from_file_location("node_source_span", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    assert module.down_revision == "20261030_vc_idempotent_key"
    source = path.read_text(encoding="utf-8")
    assert source.count("ADD COLUMN IF NOT EXISTS") == 2
    assert "DEFAULT" not in source and "NOT NULL" not in source
