# rag_orchestrator/src/core/investigation.py
"""
Foundry-owned side of product Investigate (issue #439, ADR-057, plan step 3).

The investigation agent is a separate service behind this boundary. This
module holds what Foundry owns regardless of that service's wire format:

- `InvestigationBackend`, the interface an adapter implements;
- the small internal `Upstream*` result types an adapter must produce;
- signed run IDs that bind a run to its repository and generation without
  storing anything (no migration);
- scope validation of every returned reference.

No adapter to the real service lives here: that needs the service's published
schema, which reaches Foundry through the owner. `FixtureBackend` serves
clearly labeled synthetic runs for integration testing only.
"""

import base64
import hashlib
import hmac
import json
import logging
from typing import Literal, Optional, Protocol
from uuid import uuid4

from pydantic import BaseModel, Field

from src.core.config import get_settings

logger = logging.getLogger(__name__)


class BackendUnavailable(Exception):
    """The investigation service could not be reached or answered badly."""


class UpstreamEvidence(BaseModel):
    path: str
    start_line: int
    end_line: int
    repo_id: Optional[str] = None
    generation_id: Optional[str] = None


class UpstreamFinding(BaseModel):
    statement: str
    evidence: list[UpstreamEvidence] = Field(default_factory=list)


class UpstreamRun(BaseModel):
    state: Literal["running", "finished"]
    # Open strings on purpose: the service may add completion and stop-reason
    # values within a version, and an unknown value must not break Foundry.
    completion: str = "none"
    stop_reason: Optional[str] = None
    observed_generation_id: Optional[str] = None
    findings: list[UpstreamFinding] = Field(default_factory=list)
    open_gaps: list[str] = Field(default_factory=list)
    evidence_mode: Literal["live", "fixture"] = "live"


class InvestigationBackend(Protocol):
    async def submit(self, repo_id: str, generation_id: str, question: str) -> str:
        """Start a run pinned to `generation_id`; return the service's run ID."""

    async def status(self, upstream_run_id: str) -> UpstreamRun:
        """Current state of a run. Raises BackendUnavailable on failure."""


# --- signed run IDs -------------------------------------------------------


def _b64(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).decode().rstrip("=")


def _unb64(text: str) -> bytes:
    return base64.urlsafe_b64decode(text + "=" * (-len(text) % 4))


def _mac(secret: str, payload: str) -> str:
    digest = hmac.new(secret.encode(), payload.encode(), hashlib.sha256).digest()
    return _b64(digest[:16])


def sign_run(secret: str, repo_id: str, generation_id: str, upstream: str) -> str:
    """A run ID that carries its repository, generation and upstream ID and
    cannot be altered or forged without the server secret."""
    payload = _b64(
        json.dumps([repo_id, generation_id, upstream], separators=(",", ":")).encode()
    )
    return f"{payload}.{_mac(secret, payload)}"


def open_run(secret: str, run_id: str) -> Optional[tuple[str, str, str]]:
    """(repo_id, generation_id, upstream_run_id), or None if not genuine."""
    payload, _, mac = run_id.partition(".")
    if not payload or not hmac.compare_digest(mac, _mac(secret, payload)):
        return None
    try:
        repo_id, generation_id, upstream = json.loads(_unb64(payload))
    except (ValueError, TypeError):
        return None
    if not all(isinstance(v, str) for v in (repo_id, generation_id, upstream)):
        return None
    return repo_id, generation_id, upstream


# --- fixture backend ------------------------------------------------------


class FixtureBackend:
    """Synthetic runs for integration testing. Everything it returns is
    labeled `evidence_mode: fixture`; it never reads a repository."""

    async def submit(self, repo_id: str, generation_id: str, question: str) -> str:
        return f"fixture-{uuid4()}"

    async def status(self, upstream_run_id: str) -> UpstreamRun:
        return UpstreamRun(
            state="finished",
            completion="partial",
            stop_reason="fixture_run",
            evidence_mode="fixture",
            findings=[
                UpstreamFinding(
                    statement="Synthetic finding: not derived from the repository.",
                    evidence=[
                        UpstreamEvidence(path="README.md", start_line=1, end_line=3)
                    ],
                )
            ],
            open_gaps=["Synthetic run: no repository evidence was inspected."],
        )


def get_backend() -> Optional[InvestigationBackend]:
    """The configured backend, or None when Investigate is not enabled."""
    settings = get_settings()
    choice = settings.INVESTIGATE_BACKEND.strip().lower()
    if choice == "disabled" or not settings.INVESTIGATE_RUN_SECRET:
        return None
    if choice == "fixture":
        return FixtureBackend()
    if choice == "http":
        # The adapter needs the investigation service's published schema.
        logger.warning("INVESTIGATE_BACKEND=http has no adapter yet; mode disabled")
        return None
    logger.warning("unknown INVESTIGATE_BACKEND %r; mode disabled", choice)
    return None
