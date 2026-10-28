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
