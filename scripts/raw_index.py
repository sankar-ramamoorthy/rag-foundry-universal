"""Maintain the hash index of git-ignored raw evaluation captures (issue #268).

Raw captures live in DOCS/test_results/_raw/ (git-ignored, deletable for space).
DOCS/test_results/raw-index.json is the tracked record of what existed: path,
size, sha256, who cites it and how it was produced. Reports link the index, not
the raw files, so they never dangle on a fresh clone.

    python scripts/raw_index.py update   # add/refresh entries; keeps metadata
    python scripts/raw_index.py verify   # compare local files with the index
"""

from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
RAW = ROOT / "DOCS/test_results/_raw"
INDEX = ROOT / "DOCS/test_results/raw-index.json"
METADATA_FIELDS = ("produced_by", "cited_by", "notes")


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1 << 20), b""):
            digest.update(block)
    return digest.hexdigest()


def load() -> dict:
    if INDEX.exists():
        return json.loads(INDEX.read_text(encoding="utf-8"))
    return {"root": "DOCS/test_results/_raw", "files": {}}


def update() -> int:
    index = load()
    files = index["files"]
    for path in sorted(p for p in RAW.rglob("*") if p.is_file()):
        rel = path.relative_to(RAW).as_posix()
        entry = files.get(rel, {})
        entry.update(bytes=path.stat().st_size, sha256=sha256(path))
        for field in METADATA_FIELDS:
            entry.setdefault(field, "")
        files[rel] = entry
    index["files"] = dict(sorted(files.items()))
    INDEX.write_text(json.dumps(index, indent=2) + "\n", encoding="utf-8")
    print(f"{len(files)} entries in {INDEX.relative_to(ROOT).as_posix()}")
    return 0


def verify() -> int:
    bad = 0
    for rel, entry in load()["files"].items():
        path = RAW / rel
        if not path.exists():
            print(f"absent    {rel} (cleared locally; index keeps the record)")
        elif sha256(path) != entry["sha256"]:
            print(f"MISMATCH  {rel}")
            bad += 1
        else:
            print(f"ok        {rel}")
    return 1 if bad else 0


if __name__ == "__main__":
    commands = {"update": update, "verify": verify}
    if len(sys.argv) != 2 or sys.argv[1] not in commands:
        sys.exit(__doc__)
    sys.exit(commands[sys.argv[1]]())
