"""
Deterministic Entity ID Builder for Unified Artifact Graph

Generates canonical IDs for documents, code entities, ADRs, etc.

Follows ADR-031: Canonical Identity Model.
"""

from __future__ import annotations

from pathlib import Path
import uuid
def build_canonical_id(
    relative_path: str,
    symbol_path: str | None = None
) -> str:
    """
    Build a deterministic canonical ID for an artifact.

    Args:
        relative_path: path relative to repository root (forward slashes, no leading slash)
        symbol_path: optional dot-separated symbol path (for classes, functions, methods)

    Returns:
        canonical_id: deterministic string
    """
    path_clean = relative_path.replace("\\", "/").strip("/")
    if symbol_path:
        symbol_clean = symbol_path.strip()
        return f"{path_clean}#{symbol_clean}"
    return path_clean


def build_global_id(repo_id: str, relative_path: str, symbol_path: str | None = None) -> tuple[str, str]:
    """
    Returns a tuple (repo_id, canonical_id) suitable for storage in document_nodes.

    Args:
        repo_id: UUID string of the repository
        relative_path: relative path to the artifact
        symbol_path: optional symbol path

    Returns:
        tuple: (repo_id, canonical_id)
    """
    canonical_id = build_canonical_id(relative_path, symbol_path)
    return (repo_id, canonical_id)

def build_repo_id(repo_url: str) -> str:
    """
    Deterministic repository identity.
    Same repo URL always generates same UUID.
    """
    normalized = repo_url.strip().lower().rstrip("/")
    if normalized.endswith(".git"):
        normalized = normalized[:-4]

    return str(uuid.uuid5(uuid.NAMESPACE_URL, normalized))