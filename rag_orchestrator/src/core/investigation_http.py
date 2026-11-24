# rag_orchestrator/src/core/investigation_http.py
"""
HTTP adapter from Foundry to the separate investigation service (issue #439).

Built from the service's published OpenAPI artifact, version 0.3.0-draft, which
the owner released for this work (SHA-256 as read
2307417de0915653dfabefef5f9d8ece6be2d2b9ddd750dd629edbea79a0a95d). The artifact
itself is not part of this repository.

What the adapter guarantees:
- the service address and bearer token are used only here. They never appear in
  an exception message, in anything this adapter logs, or in anything returned
  to the browser. (The httpx library itself logs each request URL at INFO, as it
  does for every service call in the orchestrator; the token is never in a URL.)
- every run ID is checked to be a UUID before it is placed in a path;
- a response larger than the service's documented limit is refused;
- unknown error codes, completion values and stop reasons are tolerated (the
  schema says clients must), while a malformed or unexpected body is refused;
- the evidence a completed run returns is converted to Foundry's own types and
  scope-checked by the caller; nothing from the service is trusted for scope.
"""

import logging
from typing import Literal, Optional
from urllib.parse import quote
from uuid import UUID, uuid4

import httpx
from pydantic import BaseModel, Field, ValidationError

from src.core.investigation import (
    BackendBusy,
    BackendRefused,
    BackendUnavailable,
    CitationNotFound,
    RunFailed,
    UpstreamCitation,
    UpstreamEvidence,
    UpstreamFinding,
    UpstreamRun,
)

logger = logging.getLogger(__name__)

# The service documents a 262,144-byte response limit; allow headroom for
# framing but refuse anything near unbounded.
MAX_RESPONSE_BYTES = 524_288
REQUEST_TIMEOUT = httpx.Timeout(30.0)

EvidenceMode = Literal["live", "fixture"]


# --- response shapes (extra fields are ignored; the service may add some) -----


class _Citation(BaseModel):
    model_config = {"extra": "ignore"}

    id: str
    repo_id: str
    generation_id: str
    path: str
    start_line: int
    end_line: int


class _Finding(BaseModel):
    model_config = {"extra": "ignore"}

    statement: str
    citations: list[_Citation] = Field(default_factory=list)


class _Unsupported(BaseModel):
    model_config = {"extra": "ignore"}

    statement: str
    reasons: list[str] = Field(default_factory=list)


class _Answer(BaseModel):
    model_config = {"extra": "ignore"}

    completion: str
    stop_reason: str
    findings: list[_Finding] = Field(default_factory=list)
    unresolved: list[str] = Field(default_factory=list)
    limitations: list[str] = Field(default_factory=list)
    unsupported: list[_Unsupported] = Field(default_factory=list)
    rejected_citations: list[dict] = Field(default_factory=list)


class _Provenance(BaseModel):
    model_config = {"extra": "ignore"}

    generation_id: str


class _Failure(BaseModel):
    model_config = {"extra": "ignore"}

    code: str


class _Run(BaseModel):
    model_config = {"extra": "ignore"}

    status: str
    evidence_mode: EvidenceMode
    provenance: Optional[_Provenance] = None
    answer: Optional[_Answer] = None
    failure: Optional[_Failure] = None


class _Submitted(BaseModel):
    model_config = {"extra": "ignore"}

    run_id: str


class _CitationBody(BaseModel):
    model_config = {"extra": "ignore"}

    citation: _Citation
    text: str
    evidence_mode: EvidenceMode


def _uuid_or_unavailable(value: str) -> str:
    try:
        return str(UUID(value))
    except (ValueError, AttributeError, TypeError) as exc:
        raise BackendUnavailable("run id is not a UUID") from exc


def _error_code(response: httpx.Response) -> str:
    """The service's `detail.code`, or an empty string. Never raises."""
    try:
        detail = response.json().get("detail")
        code = detail.get("code") if isinstance(detail, dict) else None
        return code if isinstance(code, str) else ""
    except (ValueError, AttributeError):
        return ""


class HttpInvestigationBackend:
    def __init__(
        self,
        base_url: str,
        token: str,
        model_alias: str,
        *,
        transport: Optional[httpx.AsyncBaseTransport] = None,
    ):
        base = base_url.strip().rstrip("/")
        if not base.startswith(("http://", "https://")):
            raise ValueError("the investigation service URL must be http or https")
        self._base = base
        self._token = token
        self._alias = model_alias
        self._transport = transport

    def __repr__(self) -> str:  # never print the address or token
        return "HttpInvestigationBackend(<configured>)"

    # --- transport ---------------------------------------------------------

    async def _request(
        self, method: str, path: str, *, json: Optional[dict] = None, headers=None
    ) -> httpx.Response:
        merged = {"Authorization": f"Bearer {self._token}", **(headers or {})}
        try:
            async with httpx.AsyncClient(
                timeout=REQUEST_TIMEOUT, transport=self._transport
            ) as client:
                response = await client.request(
                    method, f"{self._base}{path}", json=json, headers=merged
                )
        except httpx.HTTPError as exc:
            # Only the exception type is logged: its text can hold the address.
            logger.warning("investigation service unreachable: %s", type(exc).__name__)
            raise BackendUnavailable(
                "the investigation service is unreachable"
            ) from exc
        if len(response.content) > MAX_RESPONSE_BYTES:
            logger.warning("investigation service response exceeded the size cap")
            raise BackendUnavailable("the investigation response was too large")
        return response

    def _fail(self, response: httpx.Response, *, citation: bool = False):
        """Translate a non-success response into one of Foundry's exceptions."""
        status, code = response.status_code, _error_code(response)
        logger.warning("investigation service answered %s %s", status, code or "-")
        if status == 401:
            # A rejected token is an operator problem; say nothing about it.
            raise BackendUnavailable("authorization to the service failed")
        if status == 409 and code == "run_in_progress":
            raise BackendBusy("another investigation is running")
        if status == 409 and code == "run_authorization_used":
            raise BackendRefused(
                "This deployment has no further investigation runs available."
            )
        if status == 422 and code == "unavailable_selection":
            raise BackendRefused(
                "The investigation service cannot use the configured model."
            )
        if status == 404 and citation and code == "citation_not_found":
            raise CitationNotFound(code)
        raise BackendUnavailable(f"the investigation service answered {status}")

    @staticmethod
    def _parse(model, response: httpx.Response):
        try:
            body = response.json()
            if not isinstance(body, dict):
                raise ValueError("not an object")
            return model.model_validate(body)
        except (ValueError, ValidationError) as exc:
            logger.warning("investigation service sent an unexpected body")
            raise BackendUnavailable(
                "the investigation response was malformed"
            ) from exc

    # --- the interface -----------------------------------------------------

    async def submit(self, repo_id: str, generation_id: str, question: str) -> str:
        response = await self._request(
            "POST",
            "/v1/investigations",
            json={
                "repo_id": repo_id,
                "question": question,
                "model_alias": self._alias,
                # The generation the user was shown: the service ends the run
                # `stale_generation` before any model call if it differs.
                "expected_generation_id": generation_id,
            },
            # A fresh key per user action: a retry by Foundry is never a replay.
            headers={"Idempotency-Key": str(uuid4())},
        )
        if response.status_code not in (200, 202):
            self._fail(response)
        return _uuid_or_unavailable(self._parse(_Submitted, response).run_id)

    async def status(self, upstream_run_id: str) -> UpstreamRun:
        run_id = _uuid_or_unavailable(upstream_run_id)
        response = await self._request("GET", f"/v1/investigations/{run_id}")
        if response.status_code != 200:
            self._fail(response)
        run = self._parse(_Run, response)

        if run.status in ("queued", "running"):
            return UpstreamRun(state="running", evidence_mode=run.evidence_mode)
        if run.status == "failed":
            raise RunFailed(run.failure.code if run.failure else "unknown")
        if run.status != "completed" or run.answer is None or run.provenance is None:
            raise BackendUnavailable("the investigation response was unexpected")

        answer = run.answer
        gaps = list(answer.unresolved)
        for item in answer.unsupported:
            why = f" ({'; '.join(item.reasons)})" if item.reasons else ""
            gaps.append(f"Unsupported statement: {item.statement}{why}")
        limitations = list(answer.limitations)
        if answer.rejected_citations:
            limitations.append(
                f"{len(answer.rejected_citations)} citation(s) were rejected "
                "during verification and are not shown"
            )
        return UpstreamRun(
            state="finished",
            completion=answer.completion,
            stop_reason=answer.stop_reason,
            observed_generation_id=run.provenance.generation_id,
            findings=[
                UpstreamFinding(
                    statement=finding.statement,
                    evidence=[
                        UpstreamEvidence(
                            path=c.path,
                            start_line=c.start_line,
                            end_line=c.end_line,
                            repo_id=c.repo_id,
                            generation_id=c.generation_id,
                            citation_id=c.id,
                        )
                        for c in finding.citations
                    ],
                )
                for finding in answer.findings
            ],
            open_gaps=gaps,
            limitations=limitations,
            evidence_mode=run.evidence_mode,
        )

    async def citation(
        self, upstream_run_id: str, citation_id: str
    ) -> UpstreamCitation:
        run_id = _uuid_or_unavailable(upstream_run_id)
        response = await self._request(
            "GET",
            f"/v1/investigations/{run_id}/citations/{quote(citation_id, safe='')}",
        )
        if response.status_code != 200:
            self._fail(response, citation=True)
        body = self._parse(_CitationBody, response)
        c = body.citation
        return UpstreamCitation(
            repo_id=c.repo_id,
            generation_id=c.generation_id,
            path=c.path,
            start_line=c.start_line,
            end_line=c.end_line,
            text=body.text,
            evidence_mode=body.evidence_mode,
        )
