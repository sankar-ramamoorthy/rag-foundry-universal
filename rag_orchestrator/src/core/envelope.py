# rag_orchestrator/src/core/envelope.py
"""
Evidence envelope (issue #406, specs/011-evidence-envelope).

One additive `envelope` object on every evidence-bearing response: schema
version, repository, the generation the evidence came from, that generation's
commit (or an explicit null with the reason), a coverage level and a list of
limitations. Nothing here changes retrieval, ranking or generation; it only
describes what the service already knows.

`coverage` describes coverage of what was asked for, not of the repository.
"""

import logging
from typing import Any, Literal, Mapping, Optional, Sequence

import httpx
from pydantic import BaseModel, Field

from src.core.config import get_settings

logger = logging.getLogger(__name__)

SCHEMA_VERSION = "1"
Coverage = Literal["complete", "partial", "unknown"]

COMMIT_NOT_RECORDED = "commit_sha not recorded for this generation"
GRAPH_LIMITATION = (
    "indexed static relationships at this generation, not runtime behavior"
)
RAG_LIMITATION = "ranked, bounded retrieval: evidence is a subset of the repository"


class EvidenceEnvelope(BaseModel):
    schema_version: str = SCHEMA_VERSION
    repo_id: str
    generation_id: Optional[str] = None
    commit_sha: Optional[str] = None
    coverage: Coverage = "unknown"
    limitations: list[str] = Field(default_factory=list)


async def _real_fetch_commit_sha(
    repo_id: str, generation_id: str
) -> tuple[Optional[str], list[str]]:
    """Commit recorded for `generation_id`, plus limitation strings explaining
    a null. Never raises: a missing commit must not fail an evidence request."""
    url = f"{get_settings().INGESTION_SERVICE_URL}/v1/repos/{repo_id}/generation"
    try:
        async with httpx.AsyncClient(timeout=5) as client:
            response = await client.get(url)
        response.raise_for_status()
        data = response.json()
    except (httpx.HTTPError, ValueError) as exc:
        logger.info("envelope commit lookup failed: %s", type(exc).__name__)
        return None, ["commit_sha lookup failed"]
    if data.get("ingestion_id") != generation_id:
        return None, ["commit_sha unavailable: generation changed during request"]
    commit = data.get("commit_sha")
    if not commit:
        return None, [COMMIT_NOT_RECORDED]
    return str(commit), []


# Looked up through the module attribute so tests can replace it.
fetch_commit_sha = _real_fetch_commit_sha


async def build(
    repo_id: str,
    generation_id: Optional[str],
    coverage: Coverage,
    limitations: Sequence[str] = (),
    commit_sha: Optional[str] = None,
    commit_known: bool = False,
) -> EvidenceEnvelope:
    """Assemble an envelope. `commit_known=True` means the caller already
    holds the generation's commit (or its absence) and no lookup is needed."""
    notes = list(limitations)
    if not generation_id:
        notes.append("generation not reported by this response")
        commit_sha = None
    elif commit_known:
        if not commit_sha:
            notes.append(COMMIT_NOT_RECORDED)
            commit_sha = None
    else:
        commit_sha, commit_notes = await fetch_commit_sha(repo_id, generation_id)
        notes.extend(commit_notes)
    return EvidenceEnvelope(
        repo_id=repo_id,
        generation_id=generation_id,
        commit_sha=commit_sha,
        coverage=coverage,
        limitations=notes,
    )


# --- coverage rules (see the spec's table) ---


def rag_coverage(plan: Mapping[str, Any]) -> tuple[Coverage, list[str]]:
    if not plan.get("generation_id"):
        return "unknown", []
    if plan.get("strategy") == "python_inventory":
        completion = plan.get("completion")
        if completion == "verified_complete":
            return "complete", []
        if completion == "budget_limited":
            return "partial", ["inventory stopped at a request budget"]
        return "unknown", [f"inventory did not complete ({completion})"]
    return "partial", [RAG_LIMITATION]


def evidence_coverage(
    status: str, missing_obligations: Sequence[str]
) -> tuple[Coverage, list[str]]:
    coverage: Coverage = {
        "satisfied": "complete",
        "partial": "partial",
    }.get(status, "unknown")  # type: ignore[assignment]
    return coverage, [f"unmet obligation: {m}" for m in missing_obligations]


def orient_coverage(
    gaps: Sequence[Mapping[str, Any]], heuristic_fields: Sequence[str]
) -> tuple[Coverage, list[str]]:
    notes = [
        f"{g.get('category', 'gap')}: {g.get('reason', 'unspecified')}"
        for g in gaps
    ]
    notes.extend(f"heuristic field: {name}" for name in heuristic_fields)
    return ("partial" if gaps else "complete"), notes


def graph_coverage(
    truncated: bool, depth_limited: bool = False
) -> tuple[Coverage, list[str]]:
    notes = [GRAPH_LIMITATION]
    if truncated:
        notes.append("result truncated at a node or candidate cap")
    if depth_limited:
        notes.append("traversal stopped at the depth limit")
    return ("partial" if truncated or depth_limited else "complete"), notes
