"""Independently verify a ready generation's Compose bytes against a Git commit.

Example:
  python scripts/verify_repo_compose_snapshot.py --ingestion-url http://localhost:8001 \
    --repo-id UUID --generation-id UUID --source-checkout /path/to/repo

The checkout must contain the recorded commit; its current HEAD need not match.
This checks every Compose file exposed by the generation-scoped snapshot API.
It does not attest to other ingested files or the runtime revision.
"""

import argparse
import hashlib
import json
import re
import subprocess
from pathlib import Path, PurePosixPath
from urllib.parse import quote
from urllib.request import urlopen


SHA_RE = re.compile(r"[0-9a-f]{40}")
DIGEST_RE = re.compile(r"[0-9a-f]{64}")


def _get_json(url: str) -> dict:
    with urlopen(url, timeout=30) as response:
        result = json.load(response)
    if not isinstance(result, dict):
        raise ValueError(f"Expected JSON object from {url}")
    return result


def _git_bytes(checkout: Path, commit: str, path: str) -> bytes:
    relative = PurePosixPath(path)
    if (
        relative.is_absolute()
        or not relative.parts
        or any(part in {".", ".."} or ":" in part for part in relative.parts)
        or "\\" in path
    ):
        raise ValueError(f"Unsafe snapshot path: {path!r}")
    return subprocess.check_output(
        ["git", "-C", str(checkout), "show", f"{commit}:{path}"],
        stderr=subprocess.PIPE,
        timeout=30,
    )


def verify_snapshot(
    ingestion_url: str, repo_id: str, generation_id: str, checkout: Path
) -> dict:
    base = f"{ingestion_url.rstrip('/')}/v1/repos/{quote(repo_id, safe='')}"
    generation_url = f"{base}/generation"
    before = _get_json(generation_url)
    if (
        before.get("repo_id") != repo_id
        or before.get("ingestion_id") != generation_id
        or before.get("generation_status") != "ready"
    ):
        raise ValueError("Requested generation is not the current ready generation")
    commit = before.get("commit_sha")
    if not isinstance(commit, str) or not SHA_RE.fullmatch(commit):
        raise ValueError("Ready generation has no verifiable Git source commit")

    snapshot = _get_json(
        f"{base}/compose-snapshot?generation_id={quote(generation_id, safe='')}"
    )
    if (
        snapshot.get("repo_id") != repo_id
        or snapshot.get("ingestion_id") != generation_id
        or snapshot.get("generation_status") != "ready"
        or snapshot.get("commit_sha") != commit
    ):
        raise ValueError("Compose snapshot identity differs from pinned generation")
    documents = snapshot.get("compose_documents")
    if not isinstance(documents, dict) or not documents:
        raise ValueError("No Compose documents available for independent verification")

    checked = []
    for path, entry in sorted(documents.items()):
        if not isinstance(path, str) or not isinstance(entry, dict):
            raise ValueError("Invalid Compose snapshot entry")
        expected = entry.get("sha256")
        if not isinstance(expected, str) or not DIGEST_RE.fullmatch(expected):
            raise ValueError(f"Invalid SHA-256 for {path}")
        actual = hashlib.sha256(_git_bytes(checkout, commit, path)).hexdigest()
        checked.append(
            {
                "path": path,
                "recorded_sha256": expected,
                "source_commit_sha256": actual,
                "matches": actual == expected,
            }
        )

    after = _get_json(generation_url)
    if after != before:
        raise ValueError("Generation changed during verification")
    return {
        "repo_id": repo_id,
        "generation_id": generation_id,
        "source_commit": commit,
        "scope": "all exposed Compose snapshots only",
        "files": checked,
        "verified": all(item["matches"] for item in checked),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--ingestion-url", required=True)
    parser.add_argument("--repo-id", required=True)
    parser.add_argument("--generation-id", required=True)
    parser.add_argument("--source-checkout", required=True, type=Path)
    parser.add_argument(
        "--output", type=Path, help="Write the JSON result to this file"
    )
    args = parser.parse_args()
    try:
        result = verify_snapshot(
            args.ingestion_url,
            args.repo_id,
            args.generation_id,
            args.source_checkout,
        )
    except (OSError, ValueError, subprocess.SubprocessError) as exc:
        result = {"verified": False, "error": str(exc)}
    rendered = json.dumps(result, indent=2, sort_keys=True) + "\n"
    if args.output:
        args.output.write_text(rendered, encoding="utf-8")
    print(rendered, end="")
    return 0 if result["verified"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
