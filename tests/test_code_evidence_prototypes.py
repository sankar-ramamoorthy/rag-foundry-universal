"""Prototype invariants; no network or generation calls."""

import importlib.util
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
SPEC = importlib.util.spec_from_file_location(
    "code_prototypes", ROOT / "scripts/code_evidence_prototypes.py"
)
assert SPEC is not None and SPEC.loader is not None
prototype = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(prototype)
sys.path.pop(0)


def test_discovery_only_reorders_existing_symbols():
    original = ["docs/guide.md#run", "src/a.py#other", "src/a.py#run"]
    result = prototype.rerank(original, "Explain `run` in src/a.py")
    assert result[0] == "src/a.py#run"
    assert sorted(result) == sorted(original)


def test_allocation_deduplicates_only_same_file():
    chunks = [
        {"canonical_id": "docs-archive/a.md", "text": "historical"},
        {"canonical_id": "src/a.py#run", "text": "result = work()"},
        {"canonical_id": "src/a.py", "text": "result = work()"},
        {"canonical_id": "src/b.py#run", "text": "result = work()"},
    ]
    result = prototype.allocate(chunks, "Explain run")
    assert len(result) == 3
    assert result[0] is chunks[1]
    assert chunks[3] in result
    assert result[-1] is chunks[0]


def test_passage_window_retains_contiguous_original_chunks():
    chunks = [
        {
            "chunk_id": str(i),
            "metadata": {"chunk_index": i},
            "text": "result = budget + tokens" if i == 7 else "value = 1",
        }
        for i in range(12)
    ]
    selected = prototype.window(list(reversed(chunks)), "budget tokens")
    ordinals = [c["metadata"]["chunk_index"] for c in selected]
    assert len(selected) == 5
    assert ordinals == list(range(ordinals[0], ordinals[0] + 5))
    assert 7 in ordinals
    assert all(c is chunks[c["metadata"]["chunk_index"]] for c in selected)
