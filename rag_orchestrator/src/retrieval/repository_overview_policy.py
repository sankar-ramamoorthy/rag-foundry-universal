"""Narrow authority policy for ``claim_type=repository_overview``.

This is deliberately not a ranker, provenance score, or generic router. It
adds a deterministic repository-subject/authority envelope to the generation
context and reports an explicit gap when current structural inventory is
unavailable.
"""

import json
from typing import Any

POLICY_VERSION = "repository-overview-authority-v1"
_NON_CURRENT_ROLES = frozenset({"design", "historical", "example_fixture"})
_HISTORICAL_PATH_MARKERS = (
    "docs-archive/",
    "docs/test_results/",
    "docs/notes/",
    "test_results/",
)


def _provenance_value(entry: dict[str, Any], facet: str) -> Any:
    provenance = entry.get("provenance")
    if not isinstance(provenance, dict):
        return None
    value = provenance.get(facet)
    return value.get("value") if isinstance(value, dict) else None


def _canonical_id(entry: dict[str, Any]) -> str:
    return str(entry.get("canonical_id") or entry.get("source_label") or "")


def _entry_concerns(entry: dict[str, Any]) -> list[str]:
    canonical_id = _canonical_id(entry).lower()
    role = _provenance_value(entry, "role")
    subject = _provenance_value(entry, "subject")
    concerns: list[str] = []
    if subject == "embedded_subject":
        concerns.append("embedded_subject_cannot_satisfy_repository_overview")
    if role in _NON_CURRENT_ROLES:
        concerns.append("non_current_source_cannot_satisfy_present_structure")
    if any(marker in canonical_id for marker in _HISTORICAL_PATH_MARKERS):
        concerns.append("historical_or_evaluation_note_not_current_structure")
    return concerns


def assess_repository_overview(
    manifest: list[dict[str, Any]],
    orient_response: dict[str, Any] | None,
) -> dict[str, Any]:
    """Assess whether current structural evidence is available and safe."""
    findings = [
        {"canonical_id": _canonical_id(entry), "concerns": _entry_concerns(entry)}
        for entry in manifest
    ]
    concerns = [concern for finding in findings for concern in finding["concerns"]]
    has_inventory = isinstance(orient_response, dict)
    if not has_inventory:
        status = "gap"
        gap = "current_structural_inventory_unavailable"
    elif concerns:
        status = "qualified_with_non_authoritative_evidence"
        gap = None
    else:
        status = "qualified"
        gap = None
    return {
        "policy_version": POLICY_VERSION,
        "status": status,
        "gap": gap,
        "findings": findings,
        "inventory_present": has_inventory,
    }


def render_repository_overview_policy(
    repo_id: str,
    orient_response: dict[str, Any] | None,
    assessment: dict[str, Any],
) -> str:
    """Render deterministic instructions and inventory facts for generation."""
    inventory = json.dumps(orient_response, sort_keys=True) if orient_response else "{}"
    return (
        "REPOSITORY OVERVIEW AUTHORITY POLICY\n"
        f"Pinned repository subject: {repo_id}\n"
        "Use only facts explicitly supported by the pinned repository. "
        "Current inventory, configuration, and implementation facts outrank "
        "historical plans, evaluation notes, and fixtures. Evidence describing "
        "another repository cannot satisfy this request. Never silently change "
        "the repository subject. If the required current fact is absent, say "
        "that it is unavailable and identify the gap; do not substitute a "
        "plausible conventional layout.\n"
        f"Policy assessment: {assessment['status']}\n"
        f"Deterministic ORIENT inventory JSON: {inventory}\n"
    )
