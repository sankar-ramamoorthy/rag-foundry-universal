"""Diagnostic observers must not alter pipeline inputs or outputs."""

import importlib.util
import sys
from pathlib import Path


SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPTS))
SPEC = importlib.util.spec_from_file_location(
    "issue254_loop", SCRIPTS / "issue254_loop_diagnostic.py"
)
assert SPEC is not None and SPEC.loader is not None
diagnostic = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(diagnostic)
sys.path.pop(0)


def test_observer_returns_original_selection_and_copies_only_diagnostics():
    original = [{"chunk_id": "a", "text": "one", "metadata": {"index": 1}},
                {"chunk_id": "b", "text": "two", "metadata": {"index": 2}}]
    selected = original[:1]
    observations = []

    def selector(chunks, *, limit):
        assert chunks is original
        assert limit == 1
        return selected

    def snapshot(args, kwargs, result):
        assert args[0] is original and kwargs == {"limit": 1}
        observations.append(diagnostic.capture_chunks(result))

    observed = diagnostic.observe_sync(selector, snapshot)
    result = observed(original, limit=1)
    assert result is selected and result[0] is original[0]
    assert observations == [selected]
    observations[0][0]["metadata"]["index"] = 99
    assert original[0]["metadata"]["index"] == 1
