"""Keep explicitly requested, already retrieved sources within the context cap."""

import re
from typing import Any

from .agent_adapter import assemble_context, conservative_token_count


_PATH = re.compile(r"(?<![\w/:])([\w.-]+(?:/[\w.-]+)+)")
_FILE = re.compile(
    r"(?<![\w/.:])([\w.-]+\.(?:py|md|toml|ya?ml|json|ts|tsx|js|jsx|rs|java))"
    r"(?![\w/])",
    re.IGNORECASE,
)
_SYMBOL = re.compile(r"\b([A-Z][A-Za-z_0-9]*\.[A-Za-z_][A-Za-z_0-9]*)\b")


def _canonical(chunk: dict[str, Any]) -> str:
    value = chunk.get("canonical_id")
    return value if isinstance(value, str) else ""


def _targets(question: str) -> list[tuple[str, str]]:
    found: list[tuple[str, str]] = []
    for kind, pattern in (("path", _PATH), ("path", _FILE), ("symbol", _SYMBOL)):
        for match in pattern.finditer(question):
            target = match.group(1)
            item = (kind, target)
            if item not in found:
                found.append(item)
    # A method named inside a file path is more specific than the file.
    return sorted(found, key=lambda item: (item[0] != "symbol", question.find(item[1])))


def prioritize_exact_sources(
    chunks: list[dict[str, Any]], question: str, budget: int, *, enabled: bool = True
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    """Order unmodified chunks so resolvable explicit sources enter context first.

    A directory resolves only to a unique README under it; a qualified symbol
    resolves only to the exact canonical fragment. Ambiguity never promotes a
    guessed source. All candidates have already passed generation and policy
    selection in the caller.
    """
    if not enabled:
        return chunks, {}
    targets = _targets(question)
    if not targets:
        return chunks, {}

    groups: list[list[int]] = []
    trace: list[dict[str, Any]] = []
    claimed: set[int] = set()
    for kind, target in targets:
        canonical_paths = {_canonical(c).split("#", 1)[0] for c in chunks}
        if kind == "symbol":
            matches = [
                i for i, c in enumerate(chunks)
                if _canonical(c).split("#", 1)[-1] == target
                and "#" in _canonical(c)
            ]
            identities = {_canonical(chunks[i]) for i in matches}
        elif target in canonical_paths:
            matches = [
                i for i, c in enumerate(chunks)
                if _canonical(c).split("#", 1)[0] == target
            ]
            identities = {target}
        else:
            readmes = {
                path for path in canonical_paths
                if path == f"{target}/README.md"
            }
            matches = [
                i for i, c in enumerate(chunks)
                if _canonical(c).split("#", 1)[0] in readmes
            ]
            identities = readmes
        status = "resolved" if len(identities) == 1 else (
            "ambiguous" if len(identities) > 1 else "unavailable"
        )
        if status == "resolved":
            unclaimed = [i for i in matches if i not in claimed]
            # A target larger than the full budget cannot be preserved.
            matches = [
                i for i in unclaimed
                if conservative_token_count(
                    f"[Source: {_canonical(chunks[i])}]\n{chunks[i]['text']}"
                ) <= budget
            ]
            if matches:
                groups.append(matches)
                claimed.update(matches)
            else:
                status = "too_large" if unclaimed else "already_claimed"
        trace.append({"target": target, "kind": kind, "status": status})

    # One passage per target before a second passage from any target.
    preferred: list[int] = []
    for offset in range(max((len(group) for group in groups), default=0)):
        preferred.extend(group[offset] for group in groups if offset < len(group))
    ordered = [chunks[i] for i in preferred]
    ordered.extend(chunk for i, chunk in enumerate(chunks) if i not in claimed)
    selected_ids = {id(c) for c in assemble_context(ordered, budget).chunks}
    for entry, group in zip(
        (entry for entry in trace if entry["status"] == "resolved"), groups
    ):
        entry["status"] = (
            "preserved" if any(id(chunks[i]) in selected_ids for i in group)
            else "budget_exhausted"
        )
    return ordered, {"exact_source_preservation": trace}
