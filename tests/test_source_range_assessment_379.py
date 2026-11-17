"""Offline correctness checks for the read-only #379 diagnostic, not an API."""

import importlib.util
from pathlib import Path

import pytest

SCRIPT = Path(__file__).resolve().parents[1] / "scripts/source_range_assessment_379.py"
SPEC = importlib.util.spec_from_file_location("source_range_assessment_379", SCRIPT)
assert SPEC is not None and SPEC.loader is not None
bench = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(bench)


@pytest.mark.parametrize("text", ["", "a", "a\n", "\n\n", "é\n中\nlast", "a\r\nb\n"])
def test_windows_match_lf_reference_at_every_line(text):
    lines = bench.lf_lines(text)
    for start in range(1, len(lines) + 1):
        for end in range(start, len(lines) + 1):
            calls = []

            def fetch(offset, count):
                calls.append((offset, count))
                return text[offset - 1:offset - 1 + count]

            actual, stats = bench.window_range(fetch, start, end, window=2)
            assert actual == "".join(lines[start - 1:end])
            assert stats["queries"] == len(calls)
            assert all(count == 2 for _, count in calls)


def test_window_range_refuses_oversized_line_without_collecting_whole_file():
    calls = []

    def fetch(offset, count):
        calls.append(offset)
        return "é" * count

    with pytest.raises(ValueError, match="response cap"):
        bench.window_range(fetch, 1, 1, window=16, cap=64)
    assert len(calls) == 3


def test_window_range_does_not_retain_a_giant_skipped_line():
    text = "x" * 10000 + "\nanswer\n"
    actual, stats = bench.window_range(
        lambda offset, count: text[offset - 1:offset - 1 + count],
        2, 2, window=16,
    )
    assert actual == "answer\n"
    assert stats["queries"] > 600


def test_readonly_connection_options_are_present():
    assert "default_transaction_read_only=on" in bench.CONNECTION_OPTIONS
    assert "statement_timeout=5000" in bench.CONNECTION_OPTIONS
    assert "lock_timeout=1000" in bench.CONNECTION_OPTIONS
