# ingestion_service/src/core/repo_naming.py
"""
Derive human-readable repository identity from ingestion metadata.

Issue #30 Part 5: /v1/ingest-repo already persists {git_url, local_path,
provider} in IngestionRequest.ingestion_metadata; this module turns that
into name/display_name instead of the UUID-derived labels. Works for
historical rows too — everything is recomputed from git_url/local_path.
"""
from __future__ import annotations

import re
from pathlib import PureWindowsPath
from typing import Any, Dict, Optional, Tuple


def _parse_git_url(url: str) -> Tuple[Optional[str], Optional[str]]:
    """
    Return (owner, name) from a git URL, or (None, None) if unparseable.

    Handles https://host/owner/repo(.git), scp-style
    git@host:owner/repo(.git), ssh://git@host/owner/repo, and trailing
    slashes. Owner is the second-to-last path segment when present.
    """
    cleaned = url.strip().rstrip("/")
    if cleaned.lower().endswith(".git"):
        cleaned = cleaned[:-4]

    scp_match = re.match(r"^[\w.+-]+@[\w.-]+:(.+)$", cleaned)
    scheme_match = re.match(r"^[a-zA-Z][\w+.-]*://[^/]+/(.+)$", cleaned)
    if scp_match:
        path = scp_match.group(1)
    elif scheme_match:
        path = scheme_match.group(1)
    else:
        return None, None

    segments = [s for s in path.split("/") if s]
    if not segments:
        return None, None

    name = segments[-1]
    owner = segments[-2] if len(segments) >= 2 else None
    return owner, name


def derive_repo_identity(metadata: Optional[Dict[str, Any]]) -> Dict[str, Any]:
    """
    Map ingestion metadata to display identity.

    Returns a dict with keys source_type, name, display_name, git_url,
    local_path, branch. name/display_name are None when identity cannot
    be derived — callers fall back to UUID-derived labels.
    """
    metadata = metadata or {}
    git_url = metadata.get("git_url")
    local_path = metadata.get("local_path")
    branch = metadata.get("branch")

    if git_url:
        owner, name = _parse_git_url(git_url)
        display_name = None
        if name:
            display_name = f"{owner}/{name}" if owner else name
        return {
            "source_type": "git",
            "name": name,
            "display_name": display_name,
            "git_url": git_url,
            "local_path": None,
            "branch": branch,
        }

    if local_path:
        # PureWindowsPath accepts both / and \ separators, so this also
        # handles posix-style paths recorded by dockerized ingests.
        name = PureWindowsPath(str(local_path).rstrip("/\\")).name or None
        display_name = f"{name} — {local_path}" if name else None
        return {
            "source_type": "local",
            "name": name,
            "display_name": display_name,
            "git_url": None,
            "local_path": local_path,
            "branch": branch,
        }

    return {
        "source_type": None,
        "name": None,
        "display_name": None,
        "git_url": None,
        "local_path": None,
        "branch": branch,
    }
