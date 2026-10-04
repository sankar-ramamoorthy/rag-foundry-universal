"""Narrow authority policy for ``claim_type=repository_overview``.

This is deliberately not a ranker, provenance score, or generic router. It
adds a deterministic repository-subject/authority envelope to the generation
context and reports an explicit gap when current structural inventory is
unavailable.
"""

import json
import re
from typing import Any

POLICY_VERSION = "repository-overview-authority-v1"
_NON_CURRENT_ROLES = frozenset({"design", "historical", "example_fixture"})
_HISTORICAL_PATH_MARKERS = (
    "docs-archive/",
    "docs/test_results/",
    "docs/notes/",
    "test_results/",
)
_PURPOSE_ID = "CLAUDE.md#claude_md.what_this_project_is"
_ARCHITECTURE_IDS = (
    "shared/config/service_urls.py",
    "README.md#architecture",
)


def evidence_obligation(query: str) -> str:
    """Choose an evidence obligation, never a global source score."""
    question = query.lower()
    if any(
        term in question
        for term in (
            "according to",
            "historical",
            "history",
            "the note",
            "the plan",
            "design rationale",
            "shared/smoke_repo",
            "fixture",
        )
    ):
        return "explicit_source"
    if any(
        term in question
        for term in (
            "directory",
            "package structure",
            "repo structure",
            "repository structure",
            "file structure",
            "folder structure",
        )
    ):
        return "current_structure"
    if any(
        term in question
        for term in (
            "architecture",
            "architectural",
            "service relationship",
            "service map",
        )
    ):
        return "current_architecture"
    if re.search(
        r"\b(what does|how does)\s+[A-Za-z_]\w*\.[A-Za-z_]\w*",
        query,
        re.IGNORECASE,
    ):
        return "current_behavior"
    if any(
        term in question
        for term in (
            "what is this repository about",
            "what does rag-foundry-universal do",
            "project's purpose",
            "project purpose",
            "repository purpose",
            "kinds of source",
            "what does this repository do",
        )
    ):
        return "repository_purpose"
    return "current_structure"


def canonical_evidence_ids(obligation: str) -> tuple[str, ...]:
    if obligation == "repository_purpose":
        return (_PURPOSE_ID,)
    if obligation == "current_architecture":
        return _ARCHITECTURE_IDS
    return ()


def select_current_evidence(
    chunks: list[dict[str, Any]], obligation: str
) -> tuple[list[dict[str, Any]], list[dict[str, str]]]:
    """Exclude non-current passages only for current-fact obligations."""
    if obligation == "explicit_source":
        return chunks, []
    selected_ids = set(canonical_evidence_ids(obligation))
    has_selected_evidence = obligation in {
        "repository_purpose",
        "current_architecture",
    } and any(_canonical_id(chunk) in selected_ids for chunk in chunks)
    selected = []
    excluded = []
    for chunk in chunks:
        concerns = _entry_concerns(chunk)
        if obligation == "current_structure":
            concerns.insert(0, "orient_inventory_authoritative_for_structure")
        elif has_selected_evidence and _canonical_id(chunk) not in selected_ids:
            concerns.insert(0, "outside_selected_claim_evidence")
        if concerns:
            excluded.append(
                {
                    "canonical_id": _canonical_id(chunk),
                    "reason": concerns[0],
                }
            )
        else:
            selected.append(chunk)
    return selected, excluded


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
    obligation: str = "current_structure",
    repository_name: str | None = None,
) -> str:
    """Render deterministic instructions and inventory facts for generation."""
    inventory = json.dumps(orient_response, sort_keys=True) if orient_response else "{}"
    services = orient_response.get("services", []) if orient_response else []
    service_names = sorted(
        {
            str(service["name"])
            for service in services
            if isinstance(service, dict) and service.get("name")
        }
    )
    service_count = (
        f"{len(service_names)} distinct service names, "
        f"{len(services)} Compose declarations: {', '.join(service_names)}. "
        "A service repeated in test and main Compose files is one name.\n"
    )
    manifests = (
        {
            str(item["path"])
            for item in orient_response.get("manifests", [])
            if isinstance(item, dict) and item.get("path")
        }
        if orient_response
        else set()
    )
    test_dirs = set(orient_response.get("test_dirs", [])) if orient_response else set()
    service_facts = []
    for name in service_names:
        declarations = [
            item
            for item in services
            if isinstance(item, dict) and item.get("name") == name
        ]
        dockerfiles = sorted(
            {str(item["dockerfile"]) for item in declarations if item.get("dockerfile")}
        )
        pyproject = "yes" if f"{name}/pyproject.toml" in manifests else "not listed"
        tests = "yes" if f"{name}/tests" in test_dirs else "not listed"
        service_facts.append(
            f"{name}: Compose files "
            f"{sorted({str(item['compose_file']) for item in declarations})}; "
            f"Dockerfiles {dockerfiles or 'none listed'}; "
            f"pyproject {pyproject}; test directory {tests}"
        )
    obligation_label = {
        "repository_purpose": "project purpose and source kinds",
        "current_structure": "current directory, service, and package structure",
        "current_architecture": "current service architecture",
        "current_behavior": "current implementation behavior",
        "explicit_source": "the explicitly requested source",
    }.get(obligation, "current repository facts")
    return (
        "CURRENT REPOSITORY EVIDENCE\n"
        f"Pinned repository subject: {repo_id}\n"
        f"Verified repository name: {repository_name or 'unavailable'}\n"
        f"Question focus: {obligation_label}\n"
        f"ORIENT service count: {service_count}"
        f"Verified per-service facts: {'; '.join(service_facts)}\n"
        "Answer the user's question directly using the evidence below. "
        "Use only facts explicitly supported by the pinned repository. "
        "A Compose service does not imply a Python package, Dockerfile, "
        "or test directory. Do not generalize a property from some services "
        "to every service. Do not invent a service URL from a name or port; "
        "distinguish internal URLs from published host ports. "
        "Use current inventory for structure, current configuration and "
        "implementation for architecture or behavior, and canonical "
        "descriptions for purpose. When explicitly asked about a historical "
        "source, describe it as historical. Evidence describing "
        "another repository cannot satisfy this request. Never silently change "
        "the repository subject. If the required current fact is absent, say "
        "that it is unavailable and identify the gap; do not substitute a "
        "plausible conventional layout.\n"
        f"Policy assessment: {assessment['status']}\n"
        f"Deterministic ORIENT inventory JSON: {inventory}\n"
    )
