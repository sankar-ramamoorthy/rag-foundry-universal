"""The frozen E1 statement-level contract must match its recorded checksum (#276).

Editing the contract after freezing needs a new dated contract, not an edit.
The checksum covers the file content with LF line endings (the repository pins
the file to LF; the normalization here makes the check independent of checkout).
"""

import hashlib
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DIRECTORY = ROOT / "DOCS/evaluations/code-evidence-e1"
CONTRACT = DIRECTORY / "statement-level-contract.md"
CHECKSUM = DIRECTORY / "statement-level-contract.sha256"
ADR = ROOT / "DOCS/adr/ADR-055-node-text-read-endpoint.md"


def _text(path: Path) -> str:
    return path.read_bytes().decode("utf-8").replace("\r\n", "\n")


def test_contract_matches_its_recorded_checksum():
    recorded = CHECKSUM.read_text(encoding="utf-8").strip()
    assert re.fullmatch(r"[0-9a-f]{64}", recorded)
    actual = hashlib.sha256(_text(CONTRACT).encode("utf-8")).hexdigest()
    assert actual == recorded, (
        "statement-level-contract.md changed after it was frozen; supersede it "
        "with a new dated contract instead of editing it"
    )


def test_contract_declares_itself_frozen_and_references_an_accepted_adr():
    contract = _text(CONTRACT)
    assert "status: frozen-before-candidate-results" in contract
    assert "status: accepted" in _text(ADR)
    assert "ADR-055" in contract


def test_go_rate_is_not_decided_inside_the_frozen_contract():
    """The GO threshold is deliberately left to a dated addendum."""
    contract = _text(CONTRACT)
    assert "statement-level-contract-addendum-go-rate.md" in contract
    addendum = DIRECTORY / "statement-level-contract-addendum-go-rate.md"
    if addendum.exists():  # once the owner fixes it, it must name a rate
        assert re.search(r"\d", addendum.read_text(encoding="utf-8"))


ADDENDUM = DIRECTORY / "statement-level-contract-addendum-go-rate.md"
ADDENDUM_CHECKSUM = DIRECTORY / "statement-level-contract-addendum-go-rate.sha256"


def test_go_rate_addendum_matches_its_recorded_checksum():
    recorded = ADDENDUM_CHECKSUM.read_text(encoding="utf-8").strip()
    assert re.fullmatch(r"[0-9a-f]{64}", recorded)
    actual = hashlib.sha256(_text(ADDENDUM).encode("utf-8")).hexdigest()
    assert actual == recorded, (
        "the GO-rate addendum changed after it was frozen; supersede it with a "
        "new dated addendum committed before the held-out manifest is frozen"
    )


def test_go_rate_addendum_binds_to_the_exact_frozen_contract():
    contract_hash = CHECKSUM.read_text(encoding="utf-8").strip()
    assert contract_hash in _text(ADDENDUM)


def test_go_rate_addendum_states_the_chosen_rule_and_keeps_answers_out_of_it():
    text = _text(ADDENDUM)
    for needle in ("**k >= 10** of 12", "**wins >= 5**", "at least **3 of its 4**",
                   "exactly 12 cases over 3 repositories",
                   "Answer correctness (S8) does not decide GO"):
        assert needle in text, needle


HELD_OUT = ROOT / "DOCS/evaluations/code-evidence-held-out"
STRATIFICATION = HELD_OUT / "stratification.md"
STRATIFICATION_CHECKSUM = HELD_OUT / "stratification.sha256"


def test_held_out_stratification_matches_its_recorded_checksum():
    recorded = STRATIFICATION_CHECKSUM.read_text(encoding="utf-8").strip()
    assert re.fullmatch(r"[0-9a-f]{64}", recorded)
    actual = hashlib.sha256(_text(STRATIFICATION).encode("utf-8")).hexdigest()
    assert actual == recorded, (
        "the held-out stratification declaration changed after it was frozen; "
        "supersede it with a new dated declaration committed before the "
        "repository-selection record"
    )


def test_held_out_stratification_keeps_the_declared_shape_and_exclusions():
    text = _text(STRATIFICATION)
    for needle in ("exactly 12 cases over exactly 3 repositories",
                   "rag-foundry-universal and py-coding-agent",
                   "Take the first repository, in star order, that passes the scan",
                   "must **never** be added", "byte cost"):
        assert needle in text, needle
