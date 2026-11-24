# rag_orchestrator/tests/test_product_investigate.py
"""
Issue #439 / specs/016-product-frontend: the Foundry-owned side of Investigate.
The investigation service is replaced by a fake backend; no network or model.
"""

import asyncio
from types import SimpleNamespace

import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient

from src.api.v1 import product_investigate, product_routes
from src.api.v1.main import app
from src.core import config, investigation
from src.core.investigation import (
    BackendUnavailable,
    UpstreamEvidence,
    UpstreamFinding,
    UpstreamRun,
)

pytestmark = pytest.mark.unit

REPO = "00000000-0000-4000-8000-000000000001"
OTHER_REPO = "00000000-0000-4000-8000-000000000009"
GEN = "00000000-0000-4000-8000-000000000002"
OTHER = "00000000-0000-4000-8000-000000000003"
SECRET = "test-secret"
URL = f"/v1/product/repos/{REPO}/investigations"


def _run(**overrides):
    base = {
        "state": "finished",
        "completion": "partial",
        "stop_reason": "repeated_action",
        "findings": [
            UpstreamFinding(
                statement="Reset is handled in auth.py.",
                evidence=[
                    UpstreamEvidence(path="app/auth.py", start_line=10, end_line=14)
                ],
            )
        ],
        "open_gaps": ["email template not read"],
    }
    base.update(overrides)
    return UpstreamRun(**base)


class Fake:
    def __init__(self, run=None, submit_error=None, status_error=None):
        self.run = run or _run()
        self.submit_error = submit_error
        self.status_error = status_error
        self.submitted = []

    async def submit(self, repo_id, generation_id, question):
        if self.submit_error:
            raise self.submit_error
        self.submitted.append((repo_id, generation_id, question))
        return "upstream-1"

    async def status(self, upstream_run_id):
        if self.status_error:
            raise self.status_error
        assert upstream_run_id == "upstream-1"
        return self.run


@pytest.fixture
def setup(monkeypatch):
    state = SimpleNamespace(current=GEN, backend=Fake())

    async def current(repo_id):
        if isinstance(state.current, Exception):
            raise state.current
        return state.current

    monkeypatch.setattr(product_routes, "_current_generation", current)
    monkeypatch.setattr(product_investigate, "get_backend", lambda: state.backend)
    monkeypatch.setattr(
        product_investigate,
        "get_settings",
        lambda: SimpleNamespace(
            INVESTIGATE_RUN_SECRET=SECRET, INVESTIGATE_DEADLINE_SECONDS=1
        ),
    )
    state.client = TestClient(app)
    return state


def _start(setup, generation=GEN, question="Where is reset implemented?"):
    return setup.client.post(
        URL, json={"question": question, "generation_id": generation}
    )


def _error(response, code, status):
    assert response.status_code == status, response.text
    assert response.json()["error"]["code"] == code


# --- capabilities and gating ---


def test_capabilities_report_investigate_only_when_a_backend_exists(setup):
    assert setup.client.get("/v1/product/capabilities").json() == {
        "ask": True,
        "investigate": True,
    }
    setup.backend = None
    assert setup.client.get("/v1/product/capabilities").json()["investigate"] is False


def test_disabled_mode_is_unavailable_everywhere(setup):
    setup.backend = None
    _error(_start(setup), "unavailable", 503)
    _error(setup.client.get(f"{URL}/anything"), "unavailable", 503)


@pytest.mark.parametrize(
    "env, expected",
    [
        ({}, False),
        ({"INVESTIGATE_BACKEND": "fixture"}, False),  # no secret
        ({"INVESTIGATE_BACKEND": "fixture", "INVESTIGATE_RUN_SECRET": "x"}, True),
        ({"INVESTIGATE_BACKEND": "http", "INVESTIGATE_RUN_SECRET": "x"}, False),
        ({"INVESTIGATE_BACKEND": "nonsense", "INVESTIGATE_RUN_SECRET": "x"}, False),
    ],
)
def test_backend_selection_is_opt_in(monkeypatch, env, expected):
    for key in ("INVESTIGATE_BACKEND", "INVESTIGATE_RUN_SECRET"):
        monkeypatch.delenv(key, raising=False)
    for key, value in env.items():
        monkeypatch.setenv(key, value)
    config.reset_settings_cache()
    try:
        assert (investigation.get_backend() is not None) is expected
    finally:
        config.reset_settings_cache()


# --- start ---


def test_start_pins_the_generation_and_returns_a_running_record(setup):
    body = _start(setup).json()
    assert body["mode"] == "investigate" and body["status"] == "running"
    assert body["repo_id"] == REPO and body["generation_id"] == GEN
    assert body["run_id"]
    assert setup.backend.submitted == [(REPO, GEN, "Where is reset implemented?")]


def test_start_for_a_stale_generation_runs_nothing(setup):
    setup.current = OTHER
    response = _start(setup)
    _error(response, "stale", 409)
    assert response.json()["error"]["details"]["current_generation_id"] == OTHER
    assert setup.backend.submitted == []


@pytest.mark.parametrize("question", ["", "x" * 2001])
def test_question_limits(setup, question):
    assert _start(setup, question=question).status_code == 422
    assert setup.backend.submitted == []


def test_service_failure_on_start_is_unavailable_and_does_not_leak(setup):
    setup.backend = Fake(submit_error=BackendUnavailable("http://10.1.2.3:9 refused"))
    response = _start(setup)
    _error(response, "unavailable", 503)
    assert "10.1.2.3" not in response.text


def test_service_timeout_on_start_is_unavailable(setup):
    class Slow(Fake):
        async def submit(self, *args):
            await asyncio.sleep(5)

    setup.backend = Slow()
    _error(_start(setup), "unavailable", 503)


# --- poll ---


def _poll(setup, run_id, repo=REPO):
    return setup.client.get(f"/v1/product/repos/{repo}/investigations/{run_id}")


def test_finished_run_has_findings_gaps_and_the_stop_reason(setup):
    run_id = _start(setup).json()["run_id"]
    body = _poll(setup, run_id).json()
    assert body["status"] == "finished" and body["outcome"] == "partial"
    assert body["stop_reason"] == "repeated_action"
    assert body["open_gaps"] == ["email template not read"]
    (finding,) = body["findings"]
    (evidence,) = finding["evidence"]
    assert (evidence["start_line"], evidence["end_line"]) == (10, 14)
    assert evidence["repo_id"] == REPO and evidence["generation_id"] == GEN
    assert body["envelope"]["generation_id"] == GEN
    assert "investigation stopped: repeated_action" in body["envelope"]["limitations"]


def test_running_run_is_reported_as_running(setup):
    run_id = _start(setup).json()["run_id"]
    setup.backend.run = UpstreamRun(state="running")
    body = _poll(setup, run_id).json()
    assert body["status"] == "running" and body["findings"] == []


def test_none_outcome_with_no_findings_is_a_normal_result(setup):
    run_id = _start(setup).json()["run_id"]
    setup.backend.run = _run(
        completion="none", stop_reason="invalid_model_output", findings=[], open_gaps=[]
    )
    body = _poll(setup, run_id)
    assert body.status_code == 200
    assert body.json()["outcome"] == "none" and body.json()["findings"] == []
    assert body.json()["envelope"]["coverage"] == "unknown"


def test_unknown_values_from_the_service_do_not_break_the_record(setup):
    run_id = _start(setup).json()["run_id"]
    setup.backend.run = _run(completion="brand_new_value", stop_reason="a_new_reason")
    body = _poll(setup, run_id).json()
    assert (
        body["outcome"] == "unknown" and body["completion_detail"] == "brand_new_value"
    )
    assert body["stop_reason"] == "a_new_reason"


def test_service_reported_stale_generation_is_rejected_with_the_observed_one(setup):
    run_id = _start(setup).json()["run_id"]
    setup.backend.run = _run(
        completion="none",
        stop_reason="stale_generation",
        observed_generation_id=OTHER,
        findings=[],
    )
    response = _poll(setup, run_id)
    _error(response, "stale", 409)
    assert response.json()["error"]["details"]["current_generation_id"] == OTHER


def test_generation_changing_during_the_run_is_not_published(setup):
    run_id = _start(setup).json()["run_id"]
    setup.current = OTHER
    response = _poll(setup, run_id)
    _error(response, "stale", 409)
    assert "auth.py" not in response.text


def test_fixture_runs_are_labeled_synthetic(setup):
    setup.backend = investigation.FixtureBackend()
    run_id = _start(setup).json()["run_id"]
    body = _poll(setup, run_id).json()
    assert body["evidence_mode"] == "fixture"
    assert any("synthetic" in text for text in body["envelope"]["limitations"])


# --- scope and integrity ---


@pytest.mark.parametrize(
    "evidence",
    [
        UpstreamEvidence(path="a.py", start_line=1, end_line=2, generation_id=OTHER),
        UpstreamEvidence(path="a.py", start_line=1, end_line=2, repo_id=OTHER_REPO),
        UpstreamEvidence(path="a.py", start_line=0, end_line=2),
        UpstreamEvidence(path="a.py", start_line=5, end_line=2),
        UpstreamEvidence(path="", start_line=1, end_line=2),
        UpstreamEvidence(path="a\x00b.py", start_line=1, end_line=2),
        UpstreamEvidence(path="p" * 2000, start_line=1, end_line=2),
    ],
)
def test_out_of_scope_or_invalid_evidence_withholds_the_whole_result(setup, evidence):
    run_id = _start(setup).json()["run_id"]
    setup.backend.run = _run(
        findings=[
            UpstreamFinding(statement="fine", evidence=[]),
            UpstreamFinding(statement="bad", evidence=[evidence]),
        ]
    )
    response = _poll(setup, run_id)
    _error(response, "unavailable", 503)
    assert "fine" not in response.text


def test_a_run_cannot_be_read_through_another_repository(setup):
    run_id = _start(setup).json()["run_id"]
    _error(_poll(setup, run_id, repo=OTHER_REPO), "not_found", 404)


@pytest.mark.parametrize("run_id", ["", "garbage", "a.b", "e30.AAAA"])
def test_forged_run_ids_are_not_found(setup, run_id):
    response = _poll(setup, run_id or "x")
    _error(response, "not_found", 404)


def test_a_tampered_run_id_is_not_found(setup):
    run_id = _start(setup).json()["run_id"]
    payload, _, mac = run_id.partition(".")
    tampered = payload[:-2] + ("AA" if not payload.endswith("AA") else "BB") + "." + mac
    _error(_poll(setup, tampered), "not_found", 404)


def test_run_ids_round_trip_and_bind_repo_generation_and_upstream():
    run_id = investigation.sign_run(SECRET, REPO, GEN, "up-9")
    assert investigation.open_run(SECRET, run_id) == (REPO, GEN, "up-9")
    assert investigation.open_run("another-secret", run_id) is None


def test_service_failure_while_polling_is_unavailable(setup):
    run_id = _start(setup).json()["run_id"]
    setup.backend.status_error = BackendUnavailable("refused")
    _error(_poll(setup, run_id), "unavailable", 503)


def test_repository_not_ready_maps_to_unavailable(setup):
    setup.current = HTTPException(503, "Repository is not ready; retry")
    _error(_start(setup), "unavailable", 503)
    assert setup.backend.submitted == []
