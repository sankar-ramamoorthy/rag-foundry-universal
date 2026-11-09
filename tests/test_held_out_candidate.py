"""Candidate harness (#323): offline checks only; nothing is executed."""

import hashlib
import importlib.util
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location(
    "held_out_candidate", ROOT / "scripts/held_out_candidate.py"
)
hcand = importlib.util.module_from_spec(SPEC)
sys.modules["held_out_candidate"] = hcand
SPEC.loader.exec_module(hcand)
hc = hcand.hc


def test_spec_hash_matches_recorded_file():
    text = hcand.SPEC_FILE.read_bytes().replace(b"\r\n", b"\n")
    assert hashlib.sha256(text).hexdigest() == hcand.spec_sha256()


def test_candidate_arguments_are_control_plus_one_switch_and_no_claim_type():
    inputs = hc.load_inputs()
    case = inputs.cases[0]
    entry = inputs.pin["repositories"][case["repo"]]
    control = hc.rag_arguments(case, entry)
    cand = hcand.candidate_arguments(case, entry)
    assert cand == {**control, "named_symbol_first": True}
    assert "claim_type" not in cand
    assert cand["repository_overview_claim_selection_enabled"] is False


def test_candidate_paths_never_collide_with_control():
    assert hcand.candidate_path("H1").name == "held-out-candidate-H1.json"
    assert hcand.candidate_path("H1") != hc.capture_path(1, "H1")


def test_captures_refuse_overwrite(tmp_path):
    path = tmp_path / "held-out-candidate-H1.json"
    hc.write_capture(path, {"a": 1})
    with pytest.raises(FileExistsError):
        hc.write_capture(path, {"a": 2})


def test_run_requires_confirmation_and_authorization_ref(capsys):
    assert hcand.main(["run", "--host", "http://example.invalid"]) == 1
    assert hcand.main(
        ["run", "--host", "http://example.invalid", "--execute-frozen-questions"]
    ) == 1
    assert "owner-authorization-ref" in capsys.readouterr().err
