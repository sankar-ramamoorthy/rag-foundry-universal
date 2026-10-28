"""Fail if code or config contains a Tailscale address or MagicDNS name.

Policy (issue #268): product code, reusable evaluation infrastructure and the
personal development environment stay separate. Tailnet addresses rotate and
identify personal infrastructure, so they come from environment variables or
CLI arguments, never from committed defaults.

Scans tracked and untracked-but-not-ignored files. Documentation, specs and
archived material are exempt: they record history and may mention the tailnet.

    python scripts/check_private_addresses.py            # whole repo
    python scripts/check_private_addresses.py FILE ...   # explicit files
"""

from __future__ import annotations

import re
import subprocess
import sys
from pathlib import Path

# 100.64.0.0/10 (Tailscale CGNAT range) and MagicDNS hostnames.
TAILNET = re.compile(
    r"(?<![\d.])100\.(?:6[4-9]|[7-9]\d|1[01]\d|12[0-7])(?:\.\d{1,3}){2}(?![\d.])"
    r"|\b[\w-]+\.[\w-]+\.ts\.net\b"
)

SCANNED_SUFFIXES = {".py", ".yml", ".yaml", ".toml", ".sh", ".cfg", ".ini"}
EXEMPT_PREFIXES = ("DOCS/", "specs/", "docs-archive/")
# The guard and its test necessarily spell out example addresses.
EXEMPT_FILES = {
    "scripts/check_private_addresses.py",
    "tests/test_check_private_addresses.py",
}


def candidate_files(root: Path) -> list[str]:
    out = subprocess.check_output(
        ["git", "-C", str(root), "ls-files", "--cached", "--others",
         "--exclude-standard"],
        text=True,
    )
    return [line for line in out.splitlines() if line]


def is_scanned(rel: str) -> bool:
    rel = rel.replace("\\", "/")
    if rel in EXEMPT_FILES or rel.startswith(EXEMPT_PREFIXES):
        return False
    return Path(rel).suffix in SCANNED_SUFFIXES


def find_violations(root: Path, files: list[str]) -> list[str]:
    violations = []
    for rel in files:
        if not is_scanned(rel):
            continue
        path = root / rel
        if not path.is_file():
            continue
        text = path.read_text(encoding="utf-8", errors="replace")
        for lineno, line in enumerate(text.splitlines(), 1):
            if TAILNET.search(line):
                violations.append(f"{rel}:{lineno}: {line.strip()[:100]}")
    return violations


def main(argv: list[str]) -> int:
    root = Path(__file__).resolve().parents[1]
    files = argv or candidate_files(root)
    violations = find_violations(root, files)
    if violations:
        print("Tailnet address in code/config (take it from env or a CLI arg):")
        print("\n".join(violations))
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
