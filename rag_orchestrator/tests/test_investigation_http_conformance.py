# rag_orchestrator/tests/test_investigation_http_conformance.py
"""
Issue #439: check the adapter against the investigation service's published
OpenAPI artifact (0.3.0-draft).

The artifact belongs to the other project and is not stored in this repository.
Set LAB_OPENAPI_PATH to a local copy to run these checks; without it they are
skipped, like any test that needs an external capture. They verify that

- the request the adapter sends validates against the service's SubmitRequest,
  and
- every response body the adapter's tests use validates against the service's
  own schema for that response, so the tests exercise real shapes.
"""

import asyncio
import json
import os
from pathlib import Path

import httpx
import pytest
from jsonschema import Draft202012Validator

from src.core.investigation_http import HttpInvestigationBackend
from test_investigation_http import (
    ALIAS,
    GEN,
    REPO,
    RUN,
    Service,
    active,
    citation,
    completed,
    error,
)

PATH = os.environ.get("LAB_OPENAPI_PATH")
pytestmark = [
    pytest.mark.unit,
    pytest.mark.skipif(
        not PATH or not Path(PATH).exists(),
        reason="LAB_OPENAPI_PATH is not set to the service's OpenAPI artifact",
    ),
]


def _schema():
    return json.loads(Path(PATH).read_text(encoding="utf-8"))


def _validate(name, body):
    spec = _schema()
    root = {"$ref": f"#/components/schemas/{name}", "components": spec["components"]}
    errors = list(Draft202012Validator(root).iter_errors(body))
    assert not errors, [e.message for e in errors][:3]


def test_the_artifact_is_the_version_the_adapter_was_written_against():
    assert _schema()["info"]["version"] == "0.3.0-draft"


def test_the_submit_request_validates_against_submit_request():
    svc = Service()
    svc.on("POST", "/v1/investigations", 202, {"run_id": RUN, "status": "queued"})
    backend = HttpInvestigationBackend(
        "https://svc.example", "t", ALIAS, transport=httpx.MockTransport(svc)
    )
    asyncio.run(backend.submit(REPO, GEN, "Where is reset?"))
    request = svc.requests[0]
    _validate("SubmitRequest", json.loads(request.content))
    # The Idempotency-Key header has its own documented pattern.
    spec = _schema()
    param = spec["paths"]["/v1/investigations"]["post"]["parameters"][0]
    assert Draft202012Validator(param["schema"]).is_valid(
        request.headers["idempotency-key"]
    )


@pytest.mark.parametrize(
    "schema, body",
    [
        ("SubmitResponse", {"run_id": RUN, "status": "queued"}),
        ("ActiveInvestigation", active("queued")),
        ("ActiveInvestigation", active("running")),
        ("CompletedInvestigation", completed()),
        ("Investigation", completed()),
        ("Investigation", active("running")),
        (
            "FailedInvestigation",
            active("failed", failure={"code": "worker_timeout"}),
        ),
        (
            "CitationResponse",
            {"citation": citation(), "text": "x\n", "evidence_mode": "live"},
        ),
        ("Error", error("run_in_progress")),
    ],
)
def test_the_response_bodies_used_in_the_adapter_tests_are_valid(schema, body):
    _validate(schema, body)
