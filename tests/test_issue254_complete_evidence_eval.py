"""Oracle context construction fails closed and preserves matched inputs."""

import importlib.util
import sys
from pathlib import Path

import pytest


SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPTS))
SPEC = importlib.util.spec_from_file_location(
    "complete_evidence", SCRIPTS / "issue254_complete_evidence_eval.py"
)
assert SPEC is not None and SPEC.loader is not None
experiment = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(experiment)
sys.path.pop(0)


def test_overflow_rejected_instead_of_silently_losing_a_required_excerpt():
    sources = {"src/engine.py": {"text": "input\nprovider\ntool\nfeedback"}}
    excerpts = (("src/engine.py", "Engine.run", 1, 4),)
    with pytest.raises(ValueError, match="refuse to truncate"):
        experiment.build_evidence(sources, excerpts, budget=10)
    evidence, manifest = experiment.build_evidence(sources, excerpts, budget=100)
    assert manifest[0]["text"] == sources["src/engine.py"]["text"]
    assert "feedback" in evidence


def test_only_evidence_suffix_changes_and_the_captured_payload_is_immutable():
    payload = {"context": "fixed envelope\nold evidence", "query": "same question"}
    replaced = experiment.replace_evidence(payload, "old evidence", "new evidence")
    assert payload == {"context": "fixed envelope\nold evidence",
                       "query": "same question"}
    assert replaced == {"context": "fixed envelope\nnew evidence",
                        "query": "same question"}
    with pytest.raises(ValueError, match="exact payload suffix"):
        experiment.replace_evidence(payload, "different evidence", "new evidence")
