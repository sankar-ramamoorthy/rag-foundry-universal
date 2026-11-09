"""Named-symbol-first ordering (E1, issue #323).

Implements DOCS/evaluations/code-evidence-held-out/
mechanism-spec-named-symbol-first.md (frozen). Ordering only: it never adds,
removes or rewrites a chunk. Its only inputs are the chunk list and the query
text; it has no access to settings, manifests, case ids or trace ids.
"""

import re
from typing import Any


def chunk_label(chunk: dict[str, Any]) -> str:
    metadata = chunk.get("metadata") or {}
    return str(
        chunk.get("canonical_id")
        or metadata.get("canonical_id")
        or (metadata.get("source_metadata") or {}).get("canonical_id")
        or ""
    )


def _symbol_name(label: str) -> str | None:
    """Name of a `<path>.py#<name>` code symbol label, else None."""
    path, sep, name = label.partition("#")
    if not sep or not name or not path.endswith(".py"):
        return None
    return name


def _is_named(name: str, query: str) -> bool:
    pattern = rf"(?<![A-Za-z0-9_]){re.escape(name)}(?![A-Za-z0-9_])"
    return re.search(pattern, query) is not None


def promote_named_symbol_chunks(
    chunks: list[dict[str, Any]], query: str
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    """Stable partition: chunks of code symbols named in the query come first."""
    named: set[str] = set()
    for chunk in chunks:
        label = chunk_label(chunk)
        name = _symbol_name(label)
        if name is not None and _is_named(name, query):
            named.add(label)
    if not named:
        return chunks, {
            "enabled": True,
            "promoted_labels": [],
            "promoted_chunk_count": 0,
        }
    promoted = [c for c in chunks if chunk_label(c) in named]
    rest = [c for c in chunks if chunk_label(c) not in named]
    return promoted + rest, {
        "enabled": True,
        "promoted_labels": sorted(named),
        "promoted_chunk_count": len(promoted),
    }
