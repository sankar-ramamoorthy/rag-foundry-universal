# rag_orchestrator/tests/test_investigation_http.py
"""
Issue #439: the HTTP adapter to the investigation service. The service is
replaced by an httpx mock transport that answers with bodies shaped as the
service's published schema (0.3.0-draft) describes. No network, no model.
"""

import asyncio
import json
import logging
import re
from types import SimpleNamespace
from uuid import uuid4

import httpx
import pytest
from fastapi.testclient import TestClient

from src.api.v1 import product_investigate, product_routes
from src.api.v1.main import app
from src.core import config, investigation
from src.core.investigation import (
    BackendBusy,
    BackendRefused,
    BackendUnavailable,
    CitationNotFound,
    RunFailed,
)
from src.core.investigation_http import MAX_RESPONSE_BYTES, HttpInvestigationBackend

pytestmark = pytest.mark.unit

REPO = "00000000-0000-4000-8000-000000000001"
GEN = "00000000-0000-4000-8000-000000000002"
OTHER = "00000000-0000-4000-8000-000000000003"
RUN = "11111111-1111-4111-8111-111111111111"
TOKEN = "tok-SECRET-9f3a"
HOST = "investigation.internal.example"
ALIAS = "alias-one"
SECRET = "run-secret"


def citation(cid="c1", **over):
    base = {
        "id": cid,
        "read": 0,
        "repo_id": REPO,
        "generation_id": GEN,
        "commit_sha": None,
        "path": "app/auth.py",
        "start_line": 10,
        "end_line": 14,
        "text_sha256": "a" * 64,
    }
    base.update(over)
    return base


def completed(**over):
    body = {
        "run_id": RUN,
        "status": "completed",
        "created_at": "2026-11-24T20:00:00Z",
        "updated_at": "2026-11-24T20:01:00Z",
        "repo_id": REPO,
        "model_alias": ALIAS,
        "evidence_mode": "live",
        "record_id": "r" * 16,
        "provenance": {
            "repo_id": REPO,
            "generation_id": GEN,
            "commit_sha": None,
            "client_kind": "http",
            "base_url_sha256": "b" * 64,
        },
        "stop_reason": "finished",
        "answer": {
            "completion": "partial",
            "findings": [
                {"statement": "Reset is in auth.py.", "citations": [citation()]}
            ],
            "unresolved": ["email template not read"],
            "limitations": ["one file read"],
            "unsupported": [],
            "rejected_citations": [],
            "stop_reason": "repeated_action",
        },
    }
    body.update(over)
    return body


def active(status="running", **over):
    base = {
        "run_id": RUN,
        "status": status,
        "created_at": "2026-11-24T20:00:00Z",
        "updated_at": "2026-11-24T20:00:05Z",
        "repo_id": REPO,
        "model_alias": ALIAS,
        "evidence_mode": "live",
    }
    base.update(over)
    return base


def error(code, message="m"):
    return {"detail": {"code": code, "message": message}}


class Service:
    """A scripted investigation service."""

    def __init__(self):
        self.requests = []
        self.routes = {}

    def on(self, method, path, status, body=None, headers=None):
        self.routes[(method, path)] = (status, body, headers)

    def __call__(self, request: httpx.Request) -> httpx.Response:
        self.requests.append(request)
        key = (request.method, request.url.path)
        if key not in self.routes:
            return httpx.Response(404, json=error("run_not_found"))
        status, body, headers = self.routes[key]
        if callable(body):
            body = body(request)
        if isinstance(body, bytes):
            return httpx.Response(status, content=body, headers=headers)
        return httpx.Response(status, json=body, headers=headers)


def backend(service):
    return HttpInvestigationBackend(
        f"https://{HOST}/", TOKEN, ALIAS, transport=httpx.MockTransport(service)
    )


def run(coro):
    return asyncio.run(coro)


def _own_log(caplog) -> str:
    """What Foundry's adapter logged. The httpx library separately logs each
    request URL at INFO, as it does for every service call in the orchestrator,
    so only the adapter's own records are asserted here."""
    return " | ".join(
        r.getMessage()
        for r in caplog.records
        if r.name == "src.core.investigation_http"
    )


# --- submit ---


def test_submit_sends_the_documented_request():
    svc = Service()
    svc.on("POST", "/v1/investigations", 202, {"run_id": RUN, "status": "queued"})
    got = run(backend(svc).submit(REPO, GEN, "Where is reset?"))
    assert got == RUN
    (request,) = svc.requests
    assert request.headers["authorization"] == f"Bearer {TOKEN}"
    assert re.fullmatch(r"[!-~]{1,128}", request.headers["idempotency-key"])
    assert json.loads(request.content) == {
        "repo_id": REPO,
        "question": "Where is reset?",
        "model_alias": ALIAS,
        "expected_generation_id": GEN,
    }
    assert request.url.path == "/v1/investigations"


def test_every_submit_uses_a_fresh_idempotency_key():
    svc = Service()
    svc.on("POST", "/v1/investigations", 202, {"run_id": RUN, "status": "queued"})
    b = backend(svc)
    run(b.submit(REPO, GEN, "q"))
    run(b.submit(REPO, GEN, "q"))
    keys = {r.headers["idempotency-key"] for r in svc.requests}
    assert len(keys) == 2


def test_a_replayed_run_is_accepted():
    svc = Service()
    svc.on("POST", "/v1/investigations", 200, {"run_id": RUN, "status": "running"})
    assert run(backend(svc).submit(REPO, GEN, "q")) == RUN


@pytest.mark.parametrize(
    "status, code, exc",
    [
        (409, "run_in_progress", BackendBusy),
        (409, "run_authorization_used", BackendRefused),
        (422, "unavailable_selection", BackendRefused),
        (409, "idempotency_conflict", BackendUnavailable),
        (401, "unauthorized", BackendUnavailable),
        (413, "request_too_large", BackendUnavailable),
        (422, "invalid_request", BackendUnavailable),
        (422, "a_code_added_later", BackendUnavailable),
        (500, "", BackendUnavailable),
    ],
)
def test_submit_errors_map_to_foundry_exceptions(status, code, exc):
    svc = Service()
    svc.on("POST", "/v1/investigations", status, error(code))
    with pytest.raises(exc):
        run(backend(svc).submit(REPO, GEN, "q"))


def test_a_malformed_submit_response_is_refused():
    svc = Service()
    svc.on("POST", "/v1/investigations", 202, {"status": "queued"})
    with pytest.raises(BackendUnavailable):
        run(backend(svc).submit(REPO, GEN, "q"))
    svc.on(
        "POST", "/v1/investigations", 202, {"run_id": "not-a-uuid", "status": "queued"}
    )
    with pytest.raises(BackendUnavailable):
        run(backend(svc).submit(REPO, GEN, "q"))


# --- status ---


@pytest.mark.parametrize("state", ["queued", "running"])
def test_queued_and_running_are_running(state):
    svc = Service()
    svc.on("GET", f"/v1/investigations/{RUN}", 200, active(state))
    got = run(backend(svc).status(RUN))
    assert got.state == "running" and got.evidence_mode == "live"


def test_completed_run_is_converted_to_foundry_types():
    svc = Service()
    svc.on("GET", f"/v1/investigations/{RUN}", 200, completed())
    got = run(backend(svc).status(RUN))
    assert got.state == "finished" and got.completion == "partial"
    assert got.stop_reason == "repeated_action"
    assert got.observed_generation_id == GEN
    assert got.open_gaps == ["email template not read"]
    assert got.limitations == ["one file read"]
    (finding,) = got.findings
    (ev,) = finding.evidence
    assert (ev.path, ev.start_line, ev.end_line) == ("app/auth.py", 10, 14)
    assert (ev.repo_id, ev.generation_id, ev.citation_id) == (REPO, GEN, "c1")


def test_unsupported_statements_and_rejected_citations_are_not_hidden():
    body = completed()
    body["answer"]["unsupported"] = [
        {"statement": "It also sends mail.", "reasons": ["not read", "no citation"]}
    ]
    body["answer"]["rejected_citations"] = [
        {
            "finding_statement": "x",
            "reference": {"read": 0, "start_line": 1, "end_line": 2},
            "reason": "mismatch",
        }
    ]
    svc = Service()
    svc.on("GET", f"/v1/investigations/{RUN}", 200, body)
    got = run(backend(svc).status(RUN))
    assert any("It also sends mail." in g and "not read" in g for g in got.open_gaps)
    assert any("1 citation(s) were rejected" in n for n in got.limitations)


def test_failed_run_raises_with_its_failure_code():
    svc = Service()
    svc.on(
        "GET",
        f"/v1/investigations/{RUN}",
        200,
        active("failed", failure={"code": "worker_timeout"}),
    )
    with pytest.raises(RunFailed) as caught:
        run(backend(svc).status(RUN))
    assert caught.value.code == "worker_timeout"


def test_unknown_values_are_tolerated():
    body = completed()
    body["answer"]["completion"] = "a_value_added_later"
    body["answer"]["stop_reason"] = "a_reason_added_later"
    body["a_new_top_level_field"] = {"x": 1}
    svc = Service()
    svc.on("GET", f"/v1/investigations/{RUN}", 200, body)
    got = run(backend(svc).status(RUN))
    assert got.completion == "a_value_added_later"
    assert got.stop_reason == "a_reason_added_later"


def test_fixture_runs_keep_their_label():
    svc = Service()
    svc.on("GET", f"/v1/investigations/{RUN}", 200, completed(evidence_mode="fixture"))
    assert run(backend(svc).status(RUN)).evidence_mode == "fixture"


@pytest.mark.parametrize(
    "body",
    [
        completed(evidence_mode="something_else"),
        {**completed(), "provenance": None},
        {**completed(), "answer": None},
        {**active(), "status": "a_status_added_later"},
        {"status": "completed"},
    ],
)
def test_unexpected_status_bodies_are_refused(body):
    svc = Service()
    svc.on("GET", f"/v1/investigations/{RUN}", 200, body)
    with pytest.raises(BackendUnavailable):
        run(backend(svc).status(RUN))


def test_status_rejects_a_run_id_that_is_not_a_uuid_before_any_request():
    svc = Service()
    for bad in ("../../admin", "x", RUN + "/citations", ""):
        with pytest.raises(BackendUnavailable):
            run(backend(svc).status(bad))
    assert svc.requests == []


# --- citations ---


def test_citation_returns_the_recorded_text():
    svc = Service()
    svc.on(
        "GET",
        f"/v1/investigations/{RUN}/citations/c1",
        200,
        {"citation": citation(), "text": "def reset():\n", "evidence_mode": "live"},
    )
    got = run(backend(svc).citation(RUN, "c1"))
    assert (got.generation_id, got.start_line, got.end_line) == (GEN, 10, 14)
    assert got.text == "def reset():\n"


def test_citation_ids_are_encoded_into_the_path():
    svc = Service()
    svc.on(
        "GET",
        f"/v1/investigations/{RUN}/citations/a/b",
        404,
        error("citation_not_found"),
    )
    with pytest.raises(CitationNotFound):
        run(backend(svc).citation(RUN, "a/b"))
    assert svc.requests[0].url.raw_path.endswith(b"/citations/a%2Fb")


@pytest.mark.parametrize(
    "status, code, exc",
    [
        (404, "citation_not_found", CitationNotFound),
        (404, "run_not_found", BackendUnavailable),
        (409, "run_not_ready", BackendUnavailable),
        (500, "citation_integrity_error", BackendUnavailable),
    ],
)
def test_citation_errors(status, code, exc):
    svc = Service()
    svc.on("GET", f"/v1/investigations/{RUN}/citations/c1", status, error(code))
    with pytest.raises(exc):
        run(backend(svc).citation(RUN, "c1"))


# --- transport safety ---


def test_unreachable_service_is_unavailable_and_leaks_nothing(caplog):
    def refuse(request):
        raise httpx.ConnectError(f"cannot reach https://{HOST} with {TOKEN}")

    b = HttpInvestigationBackend(
        f"https://{HOST}", TOKEN, ALIAS, transport=httpx.MockTransport(refuse)
    )
    with caplog.at_level(logging.DEBUG):
        with pytest.raises(BackendUnavailable) as caught:
            run(b.submit(REPO, GEN, "q"))
    assert HOST not in str(caught.value) and TOKEN not in str(caught.value)
    assert _own_log(caplog) == "" or (
        HOST not in _own_log(caplog) and TOKEN not in _own_log(caplog)
    )


def test_non_success_responses_leak_nothing(caplog):
    svc = Service()
    svc.on(
        "POST",
        "/v1/investigations",
        500,
        {"detail": {"code": "x", "message": f"{HOST} {TOKEN}"}},
    )
    with caplog.at_level(logging.DEBUG):
        with pytest.raises(BackendUnavailable) as caught:
            run(backend(svc).submit(REPO, GEN, "q"))
    assert HOST not in str(caught.value) and TOKEN not in str(caught.value)
    own = _own_log(caplog)
    assert own and HOST not in own and TOKEN not in own


def test_oversized_and_non_json_responses_are_refused():
    svc = Service()
    svc.on("GET", f"/v1/investigations/{RUN}", 200, b"x" * (MAX_RESPONSE_BYTES + 1))
    with pytest.raises(BackendUnavailable):
        run(backend(svc).status(RUN))
    svc.on("GET", f"/v1/investigations/{RUN}", 200, b"<html>502</html>")
    with pytest.raises(BackendUnavailable):
        run(backend(svc).status(RUN))
    svc.on("GET", f"/v1/investigations/{RUN}", 200, [1, 2, 3])
    with pytest.raises(BackendUnavailable):
        run(backend(svc).status(RUN))


def test_repr_and_construction_do_not_expose_the_address_or_token():
    b = backend(Service())
    assert HOST not in repr(b) and TOKEN not in repr(b)
    with pytest.raises(ValueError):
        HttpInvestigationBackend("ftp://example", TOKEN, ALIAS)
    with pytest.raises(ValueError):
        HttpInvestigationBackend("investigation.internal", TOKEN, ALIAS)


# --- backend selection ---


@pytest.mark.parametrize(
    "env, expected",
    [
        ({}, False),
        ({"INVESTIGATION_SERVICE_URL": "https://h"}, False),
        (
            {
                "INVESTIGATION_SERVICE_URL": "https://h",
                "INVESTIGATION_SERVICE_TOKEN": "t",
            },
            False,
        ),
        (
            {
                "INVESTIGATION_SERVICE_URL": "https://h",
                "INVESTIGATION_SERVICE_TOKEN": "t",
                "INVESTIGATION_MODEL_ALIAS": "a",
            },
            True,
        ),
    ],
)
def test_http_backend_needs_url_token_and_a_model_alias(monkeypatch, env, expected):
    for key in (
        "INVESTIGATION_SERVICE_URL",
        "INVESTIGATION_SERVICE_TOKEN",
        "INVESTIGATION_MODEL_ALIAS",
    ):
        monkeypatch.delenv(key, raising=False)
    monkeypatch.setenv("INVESTIGATE_BACKEND", "http")
    monkeypatch.setenv("INVESTIGATE_RUN_SECRET", "s")
    for key, value in env.items():
        monkeypatch.setenv(key, value)
    config.reset_settings_cache()
    try:
        got = investigation.get_backend()
        assert (got is not None) is expected
        if got is not None:
            assert isinstance(got, HttpInvestigationBackend)
    finally:
        config.reset_settings_cache()


# --- through the product routes ---


@pytest.fixture
def product(monkeypatch):
    state = SimpleNamespace(current=GEN, service=Service())

    async def current(repo_id):
        return state.current

    monkeypatch.setattr(product_routes, "_current_generation", current)
    monkeypatch.setattr(
        product_investigate, "get_backend", lambda: backend(state.service)
    )
    monkeypatch.setattr(
        product_investigate,
        "get_settings",
        lambda: SimpleNamespace(
            INVESTIGATE_RUN_SECRET=SECRET, INVESTIGATE_DEADLINE_SECONDS=5
        ),
    )
    state.client = TestClient(app)
    return state


def _start(product):
    product.service.on(
        "POST", "/v1/investigations", 202, {"run_id": RUN, "status": "queued"}
    )
    r = product.client.post(
        f"/v1/product/repos/{REPO}/investigations",
        json={"question": "Where is reset?", "generation_id": GEN},
    )
    assert r.status_code == 200, r.text
    return r.json()["run_id"]


def _poll(product, run_id):
    return product.client.get(f"/v1/product/repos/{REPO}/investigations/{run_id}")


def test_end_to_end_start_poll_and_recorded_excerpt(product):
    run_id = _start(product)
    product.service.on("GET", f"/v1/investigations/{RUN}", 200, completed())
    body = _poll(product, run_id).json()
    assert body["status"] == "finished" and body["outcome"] == "partial"
    (finding,) = body["findings"]
    assert finding["evidence"][0]["citation_id"] == "c1"
    assert "one file read" in body["envelope"]["limitations"]

    product.service.on(
        "GET",
        f"/v1/investigations/{RUN}/citations/c1",
        200,
        {
            "citation": citation(),
            "text": "def reset():\n    ...\n",
            "evidence_mode": "live",
        },
    )
    cited = product.client.get(
        f"/v1/product/repos/{REPO}/investigations/{run_id}/citations/c1"
    )
    assert cited.status_code == 200, cited.text
    assert cited.json()["text"].startswith("def reset()")
    assert cited.json()["generation_id"] == GEN


def test_supported_completion_maps_to_the_complete_outcome(product):
    run_id = _start(product)
    body = completed()
    body["answer"]["completion"] = "supported"
    body["answer"]["stop_reason"] = "finished"
    product.service.on("GET", f"/v1/investigations/{RUN}", 200, body)
    got = _poll(product, run_id).json()
    assert got["outcome"] == "complete" and got["completion_detail"] == "supported"


def test_service_reported_stale_generation_is_stale_with_the_observed_generation(
    product,
):
    run_id = _start(product)
    body = completed()
    body["provenance"]["generation_id"] = OTHER
    body["answer"].update(
        completion="none", findings=[], stop_reason="stale_generation"
    )
    product.service.on("GET", f"/v1/investigations/{RUN}", 200, body)
    r = _poll(product, run_id)
    assert r.status_code == 409 and r.json()["error"]["code"] == "stale"
    assert r.json()["error"]["details"]["current_generation_id"] == OTHER


def test_a_failed_run_is_an_unavailable_error_with_its_code(product):
    run_id = _start(product)
    product.service.on(
        "GET",
        f"/v1/investigations/{RUN}",
        200,
        active("failed", failure={"code": "worker_failed"}),
    )
    r = _poll(product, run_id)
    assert r.status_code == 503
    assert r.json()["error"]["code"] == "unavailable"
    assert r.json()["error"]["details"]["failure_code"] == "worker_failed"


def test_one_run_at_a_time_is_reported_plainly(product):
    product.service.on("POST", "/v1/investigations", 409, error("run_in_progress"))
    r = product.client.post(
        f"/v1/product/repos/{REPO}/investigations",
        json={"question": "q", "generation_id": GEN},
    )
    assert r.status_code == 503 and r.json()["error"]["code"] == "unavailable"
    assert "Another investigation is running" in r.json()["error"]["message"]


def test_the_service_address_and_token_never_reach_the_browser(product):
    product.service.on("POST", "/v1/investigations", 500, error("x", f"{HOST} {TOKEN}"))
    r = product.client.post(
        f"/v1/product/repos/{REPO}/investigations",
        json={"question": "q", "generation_id": GEN},
    )
    assert HOST not in r.text and TOKEN not in r.text


def test_a_citation_outside_the_runs_scope_is_withheld(product):
    run_id = _start(product)
    product.service.on(
        "GET",
        f"/v1/investigations/{RUN}/citations/c1",
        200,
        {
            "citation": citation(generation_id=OTHER),
            "text": "x",
            "evidence_mode": "live",
        },
    )
    r = product.client.get(
        f"/v1/product/repos/{REPO}/investigations/{run_id}/citations/c1"
    )
    assert r.status_code == 503 and "x" not in r.json()["error"]["message"]


def test_missing_citation_is_not_found_and_forged_runs_are_too(product):
    run_id = _start(product)
    product.service.on(
        "GET",
        f"/v1/investigations/{RUN}/citations/c9",
        404,
        error("citation_not_found"),
    )
    r = product.client.get(
        f"/v1/product/repos/{REPO}/investigations/{run_id}/citations/c9"
    )
    assert r.status_code == 404 and r.json()["error"]["code"] == "not_found"
    forged = product.client.get(
        f"/v1/product/repos/{REPO}/investigations/{uuid4()}/citations/c1"
    )
    assert forged.status_code == 404
