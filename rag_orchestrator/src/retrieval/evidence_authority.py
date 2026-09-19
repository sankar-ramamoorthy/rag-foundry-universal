# rag_orchestrator/src/retrieval/evidence_authority.py
"""
Stage C: authority-aware sufficiency for TRACE/IMPACT evidence
(issue #200 follow-up to #199, per the Phase 6 handoff's Stage C
section).

Pure, deterministic, opt-in: given a caller-declared claim type and
Stage A1's mechanical `EvidenceAssessment` (already computed, unchanged),
report whether the *evidence itself* is authority-qualified for that
claim -- using the exact same query-purpose-aware rules Stage B3's
shadow diagnostics already established (`provenance_diagnostics.py`),
just applied to TRACE/IMPACT's evidence items instead of `/v1/rag`'s
final-context manifest. No new policy is invented here.

This NEVER replaces, gates, or filters Stage A's mechanical assessment
-- "mechanical success and authority-qualified success must be
separately visible" (handoff). A `claim_type`-less caller gets exactly
Stage A/A2's existing behavior; this module does not run at all.

Scope: TRACE and IMPACT only. ORIENT's facets are inventory-level
aggregates, not individually-sourced artifacts the existing provenance
model attaches to -- an ORIENT authority check is not attempted here
and would need its own design, not a reuse of this one.
"""

from dataclasses import dataclass
from typing import Literal, Optional

from src.retrieval.evidence_sufficiency import EvidenceAssessment
from src.retrieval.provenance_diagnostics import (
    ClaimType,
    DiagnosticFinding,
    diagnose_manifest,
)

POLICY_VERSION = "stage-c-authority-v1"

AuthorityStatus = Literal[
    "authority_qualified",
    "authority_unqualified",
    "authority_unknown",
    "not_evaluated",
]


@dataclass(frozen=True)
class AuthorityAssessment:
    policy_version: str
    claim_type: Optional[ClaimType]
    status: AuthorityStatus
    findings: list[DiagnosticFinding]


def _overall_status(findings: list[DiagnosticFinding]) -> AuthorityStatus:
    all_concerns = [concern for finding in findings for concern in finding.concerns]
    real_concerns = [c for c in all_concerns if c != "unknown_provenance"]
    if real_concerns:
        return "authority_unqualified"
    if "unknown_provenance" in all_concerns:
        return "authority_unknown"
    return "authority_qualified"


def assess_authority(
    claim_type: Optional[ClaimType],
    assessment: EvidenceAssessment,
    provenance_by_canonical_id: dict[str, Optional[dict]],
) -> AuthorityAssessment:
    """`provenance_by_canonical_id` comes from the already-loaded, already
    generation-fenced in-memory graph (`Node.provenance`, Stage C's own
    prerequisite graph-transport extension) -- no additional I/O here."""
    if claim_type is None or not assessment.evidence:
        # Nothing declared to check against, or nothing to check --
        # "not evaluated" is honest; it is not the same as "qualified".
        return AuthorityAssessment(
            policy_version=POLICY_VERSION,
            claim_type=claim_type,
            status="not_evaluated",
            findings=[],
        )

    manifest_like = [
        {
            "canonical_id": item.identity,
            "chunk_id": item.identity,
            "provenance": provenance_by_canonical_id.get(item.identity),
        }
        for item in assessment.evidence
    ]
    findings = diagnose_manifest(claim_type, manifest_like)
    return AuthorityAssessment(
        policy_version=POLICY_VERSION,
        claim_type=claim_type,
        status=_overall_status(findings),
        findings=findings,
    )
