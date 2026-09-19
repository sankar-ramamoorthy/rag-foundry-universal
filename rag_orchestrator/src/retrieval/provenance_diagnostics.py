# rag_orchestrator/src/retrieval/provenance_diagnostics.py
"""
Provenance shadow diagnostics (issue #199, Stage B3).

Pure, deterministic, read-only: given a caller-declared claim type and
the already-finalized context manifest (Stage B2 transport), flag
per-entry provenance *concerns* -- never a score, never a filter, never
anything that changes which chunks were selected or what the LLM saw.
Computed only when a caller explicitly supplies `claim_type`; omitted by
default, so every existing caller's behavior and response shape is
unchanged (the same "additive, opt-in" shape `trace_canonical_ids`
already uses in `service.py`).

This is diagnostic-only, by explicit owner direction: "do not introduce
a universal provenance score or broad hard filtering... any policy must
be query-purpose-aware, deterministic, and justified by measured
improvement." Stage C (a `#200` follow-up) is where -- IF this shadow
pass shows a clear, measured pattern -- provenance might start actually
influencing sufficiency decisions. Nothing here does that.

Rules are deliberately narrow and lenient: a claim type with no rule
below records no concerns for it. Absent/unclassified provenance is
flagged as its own concern (`unknown_provenance`), never silently
treated as either "fine" or "suspect".
"""

from dataclasses import dataclass
from typing import Literal, Optional

ClaimType = Literal[
    "implemented_behavior",
    "design_rationale",
    "test_contract",
    "repository_overview",
]

Concern = Literal[
    "embedded_subject_offered_as_implementation",
    "non_implementation_role_offered_as_implementation",
    "superseded_source_offered_as_current",
    "embedded_subject_in_overview",
    "unknown_provenance",
]

# Roles that do not read as "this is the repository's current
# implementation" when a claim asks for implemented behavior. Deliberately
# narrow: `configuration`/`unknown_mixed` are NOT included here -- a
# config file or an unclassified artifact may well be exactly what an
# "implemented behavior" question is about, and flagging them would be
# the "broad hard filtering" this stage is explicitly not allowed to do.
_NON_IMPLEMENTATION_ROLES = frozenset(
    {"design", "documentation", "historical", "example_fixture"}
)


@dataclass(frozen=True)
class DiagnosticFinding:
    canonical_id: Optional[str]
    chunk_id: Optional[str]
    concerns: list[Concern]


def _diagnose_entry(claim_type: ClaimType, entry: dict) -> DiagnosticFinding:
    provenance = entry.get("provenance")
    concerns: list[Concern] = []

    if provenance is None:
        concerns.append("unknown_provenance")
        return DiagnosticFinding(
            canonical_id=entry.get("canonical_id"),
            chunk_id=entry.get("chunk_id"),
            concerns=concerns,
        )

    subject = provenance.get("subject", {}).get("value")
    role = provenance.get("role", {}).get("value")
    declared_status = provenance.get("validity", {}).get("declared_status")

    if claim_type == "implemented_behavior":
        if subject == "embedded_subject":
            concerns.append("embedded_subject_offered_as_implementation")
        if role in _NON_IMPLEMENTATION_ROLES:
            concerns.append("non_implementation_role_offered_as_implementation")
        if declared_status == "superseded":
            concerns.append("superseded_source_offered_as_current")
    elif claim_type == "repository_overview":
        if subject == "embedded_subject":
            concerns.append("embedded_subject_in_overview")
    # design_rationale / test_contract: no rule yet -- a design question
    # citing implementation (or vice versa) is common and not inherently
    # a problem; asserting one here without measured evidence would be
    # exactly the unjustified policy this stage must not introduce.

    return DiagnosticFinding(
        canonical_id=entry.get("canonical_id"),
        chunk_id=entry.get("chunk_id"),
        concerns=concerns,
    )


def diagnose_manifest(
    claim_type: ClaimType, manifest: list[dict]
) -> list[DiagnosticFinding]:
    """One finding per manifest entry (Stage B2's `final_context_manifest`),
    in the same order. An entry with no concerns still appears, with an
    empty `concerns` list -- silence is a recorded finding, not an
    absent one, so a diagnostic consumer can tell "checked, clean" apart
    from "never ran"."""
    return [_diagnose_entry(claim_type, entry) for entry in manifest]
