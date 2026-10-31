"""The frozen held-out snapshot clarification (#305): checksum and consistency."""

import hashlib
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
HELD_OUT = ROOT / "DOCS/evaluations/code-evidence-held-out"
DOC = HELD_OUT / "clarification-snapshot-tree-equivalence.md"
CHECKSUM = HELD_OUT / "clarification-snapshot-tree-equivalence.sha256"
RUNBOOK = HELD_OUT / "ingestion-runbook.md"
TREES = {
    "werkzeug": "93f10217a04d9b5b3367d57227d3fec46c7990b8",
    "hatch": "ab8c48bb625432f23f8035afbd1aaf7fccb8141d",
    "pdfminer": "b34c055ee8a7c23e332229bbbdc4e3c1ca8d1cf4",
}


def test_clarification_matches_its_recorded_checksum():
    text = DOC.read_bytes().replace(b"\r\n", b"\n")
    assert hashlib.sha256(text).hexdigest() == CHECKSUM.read_text().strip()


def test_tree_hashes_in_the_clarification_agree_with_the_runbook():
    document = DOC.read_text(encoding="utf-8")
    runbook = RUNBOOK.read_text(encoding="utf-8")
    for tree in TREES.values():
        assert tree in document and tree in runbook


def test_exception_is_limited_and_the_commit_rule_is_kept():
    document = " ".join(DOC.read_text(encoding="utf-8").split())
    assert "applies to such snapshots and to nothing else" in document
    assert "must report exactly those commits" in document
    assert "does not edit the frozen held-out manifest" in document
