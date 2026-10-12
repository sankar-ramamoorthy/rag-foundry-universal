"""Experimental selector checks: literal source, UTF-8 cap, no fixed ranges."""

import sys
from pathlib import Path


sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
from issue254_automatic_coverage_eval import select  # noqa: E402  # pyright: ignore[reportMissingImports]


def test_shifted_source_preserves_selection_and_source_fidelity():
    source = ('def process(prompt):\n'
              '    response = provider.invoke(prompt)\n'
              '    result = tool.execute(response)\n'
              '    return result\n')
    question = "Using `sample.py#process`, trace prompt to tool result."
    first = select({"sample.py": {"text": source}}, question)
    shifted = select({"sample.py": {"text": "\n" * 31 + source}}, question)
    assert first["evidence"] == shifted["evidence"]
    for entry in shifted["manifest"]:
        assert entry["text"] == "\n".join(
            ("\n" * 31 + source).splitlines()[
                entry["first_line"] - 1:entry["last_line"]])


def test_utf8_budget_rejects_whole_statement_without_truncation():
    source = 'def process(prompt):\n    result = tool.execute("🧪" * 2, prompt)\n'
    question = "Using `sample.py#process`, trace prompt to tool result."
    full = select({"sample.py": {"text": source}}, question)
    cost = full["evidence_bytes"]
    assert cost > len(full["evidence"])
    rejected = select({"sample.py": {"text": source}}, question, cost - 1)
    assert rejected["evidence"] == ""
    assert rejected["budget_rejected_seeds"]
    assert select({"sample.py": {"text": source}}, question, cost)[
        "evidence"] == full["evidence"]
