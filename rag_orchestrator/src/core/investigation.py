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


class BackendBusy(BackendUnavailable):
    """The service accepts one active run at a time and is running another."""


class BackendRefused(BackendUnavailable):
    """The service refused the run for a reason a user can be told about (for
    example, a deployment that allows no further runs). `message` is written by
    Foundry, never copied from the service."""

    def __init__(self, message: str):
        super().__init__(message)
        self.message = message


class RunFailed(Exception):
    """The run ended `failed` (no answer). `code` is the service's failure code;
    it is a closed vocabulary of short identifiers and is safe to show."""

    def __init__(self, code: str):
        super().__init__(code)
        self.code = code


class CitationNotFound(Exception):
    """The service has no such citation for that run."""


class UpstreamEvidence(BaseModel):
    path: str
    start_line: int
    end_line: int
    repo_id: Optional[str] = None
    generation_id: Optional[str] = None
    # The service's identifier for this citation within the run; lets Foundry
    # fetch the recorded excerpt later.
    citation_id: Optional[str] = None


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
    # Limits the service reported about its own answer (shown as envelope notes).
    limitations: list[str] = Field(default_factory=list)
    evidence_mode: Literal["live", "fixture"] = "live"


class UpstreamCitation(BaseModel):
    """A citation as recorded by the service, with its stored, verified text."""

    repo_id: str
    generation_id: str
    path: str
    start_line: int
    end_line: int
    text: str
    evidence_mode: Literal["live", "fixture"] = "live"


class InvestigationBackend(Protocol):
    async def submit(self, repo_id: str, generation_id: str, question: str) -> str:
        """Start a run pinned to `generation_id`; return the service's run ID."""

    async def status(self, upstream_run_id: str) -> UpstreamRun:
        """Current state of a run. Raises BackendUnavailable on failure and
        RunFailed when the run ended without an answer."""

    async def citation(
        self, upstream_run_id: str, citation_id: str
    ) -> UpstreamCitation:
        """The recorded, verified text of one citation. Raises CitationNotFound
        or BackendUnavailable."""


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
                        UpstreamEvidence(
                            path="README.md",
                            start_line=1,
                            end_line=3,
                            citation_id="c1",
                        )
                    ],
                )
            ],
            open_gaps=["Synthetic run: no repository evidence was inspected."],
        )

    async def citation(
        self, upstream_run_id: str, citation_id: str
    ) -> UpstreamCitation:
        if citation_id != "c1":
            raise CitationNotFound(citation_id)
        raise BackendUnavailable("the fixture backend holds no recorded text")


def get_backend() -> Optional[InvestigationBackend]:
    """The configured backend, or None when Investigate is not enabled."""
    settings = get_settings()
    choice = settings.INVESTIGATE_BACKEND.strip().lower()
    if choice == "disabled" or not settings.INVESTIGATE_RUN_SECRET:
        return None
    if choice == "fixture":
        return FixtureBackend()
    if choice == "http":
        url = settings.INVESTIGATION_SERVICE_URL.strip()
        token = settings.INVESTIGATION_SERVICE_TOKEN
        alias = settings.INVESTIGATION_MODEL_ALIAS.strip()
        if not (url and token and alias):
            # The model profile is an owner decision: there is no default alias.
            logger.warning(
                "INVESTIGATE_BACKEND=http needs the service URL, token and model "
                "alias; mode disabled"
            )
            return None
        from src.core.investigation_http import HttpInvestigationBackend

        return HttpInvestigationBackend(url, token, alias)
    logger.warning("unknown INVESTIGATE_BACKEND %r; mode disabled", choice)
    return None
