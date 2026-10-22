"""Invariants for the offline E1 feasibility oracle (#264); no network."""

import importlib.util
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location(
    "code_feasibility", ROOT / "scripts/code_evidence_feasibility.py"
)
assert SPEC is not None and SPEC.loader is not None
feasibility = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(feasibility)
RESULT = feasibility.run()


def test_reproduced_chunks_match_every_stored_baseline_chunk():
    check = RESULT["chunker_validation"]
    assert check["checked"] > 0
    assert check["mismatches"] == []


def test_every_frozen_fragment_is_located_in_one_chunk():
    for case in RESULT["cases"].values():
        assert case["unlocated_fragments"] == []
        assert case["fragments_split_across_chunks"] == []


def test_context_bytes_use_real_labels_and_separator():
    parts = [("a.py#f", "x = 1"), ("b.py#g", "y = 2")]
    expected = "[Source: a.py#f]\nx = 1\n\n[Source: b.py#g]\ny = 2"
    assert feasibility.context_bytes(parts) == len(expected.encode())


def test_exact_statements_fit_the_unchanged_cap_in_every_case():
    assert RESULT["cap_bytes"] == 4096
    for case in RESULT["cases"].values():
        assert case["fits"]["exact_statements"]
