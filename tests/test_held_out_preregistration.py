"""The frozen held-out pre-registration (#303): checksum and the claims it makes
about the frozen manifest. No network."""

import hashlib
import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
HELD_OUT = ROOT / "DOCS/evaluations/code-evidence-held-out"
DOC = HELD_OUT / "preregistration-named-symbol-first.md"
CHECKSUM = HELD_OUT / "preregistration-named-symbol-first.sha256"


def test_preregistration_matches_its_recorded_checksum():
    text = DOC.read_bytes().replace(b"\r\n", b"\n")
    assert hashlib.sha256(text).hexdigest() == CHECKSUM.read_text().strip()


def test_named_rule_applied_to_the_frozen_manifest_matches_the_document():
    manifest = json.loads((HELD_OUT / "manifest.json").read_text(encoding="utf-8"))
    named = set()
    for case in manifest["cases"]:
        name = case["primary_function"].split("#")[-1]
        pattern = r"(?<![A-Za-z0-9_])" + re.escape(name) + r"(?![A-Za-z0-9_])"
        if re.search(pattern, case["query"]):
            named.add(case["id"])
    assert named == {"H1", "H2", "H3", "P1", "P2", "P3", "W2", "W3"}
    assert named == {c["id"] for c in manifest["cases"] if c["style"] == "explicit"}
    document = DOC.read_text(encoding="utf-8")
    assert "H1, H2, H3, P1, P2, P3, W2, W3 (8" in document
