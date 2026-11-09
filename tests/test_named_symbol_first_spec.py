"""The frozen named-symbol-first mechanism specification (#323): checksum and the
integration invariant it states about the unchanged runtime. No network."""

import hashlib
import importlib.util
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
HELD_OUT = ROOT / "DOCS/evaluations/code-evidence-held-out"
DOC = HELD_OUT / "mechanism-spec-named-symbol-first.md"
CHECKSUM = HELD_OUT / "mechanism-spec-named-symbol-first.sha256"


def test_spec_matches_its_recorded_checksum():
    text = DOC.read_bytes().replace(b"\r\n", b"\n")
    assert hashlib.sha256(text).hexdigest() == CHECKSUM.read_text().strip()


def test_spec_is_frozen_and_discloses_it_was_not_blinded():
    text = DOC.read_text(encoding="utf-8")
    assert "status: frozen-before-implementation" in text
    assert "was not blinded" in text


def test_exact_source_preservation_is_disabled_at_the_call_site_by_default():
    """The spec's invariant: with the experiment's arguments the prioritizer is
    a no-op, so the partition is the order the byte allocator sees."""
    source = (ROOT / "rag_orchestrator/src/core/service.py").read_text("utf-8")
    assert 'enabled=claim_type == "repository_overview" and claim_selection' in source
    prioritizer = (
        ROOT / "rag_orchestrator/src/retrieval/exact_source_preservation.py"
    ).read_text("utf-8")
    assert "if not enabled:\n        return chunks, {}" in prioritizer


def test_the_experiment_never_passes_claim_type_and_keeps_claim_selection_off():
    spec = importlib.util.spec_from_file_location(
        "held_out_control", ROOT / "scripts/held_out_control.py"
    )
    assert spec is not None and spec.loader is not None
    hc = importlib.util.module_from_spec(spec)
    sys.modules["held_out_control"] = hc
    spec.loader.exec_module(hc)
    inputs = hc.load_inputs()
    case = inputs.cases[0]
    args = hc.rag_arguments(case, inputs.pin["repositories"][case["repo"]])
    assert "claim_type" not in args
    assert args["repository_overview_claim_selection_enabled"] is False
    assert args["rerank"] is False
