# rag_orchestrator/tests/test_product_ask.py
"""
Issue #433 / specs/016-product-frontend: generation-pinned Ask.
The RAG pipeline and generation lookup are replaced; no network or model.
"""

import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient

from src.api.v1 import product_routes
from src.api.v1.main import app
from src.api.v1.models import RAGResponse
from src.core.citations import Citation
from src.core.envelope import EvidenceEnvelope

pytestmark = pytest.mark.unit

REPO = "00000000-0000-4000-8000-000000000001"
GEN = "00000000-0000-4000-8000-000000000002"
OTHER = "00000000-0000-4000-8000-000000000003"
URL = f"/v1/product/repos/{REPO}/ask"


def _result(generation=GEN, citations=None, envelope=True):
    if citations is None:
        citations = [
            Citation(
                repo_id=REPO,
                generation_id=GEN,
                path="pkg/mod.py",
                start_line=1,
                end_line=3,
                range_reason=None,
            ),
            Citation(repo_id=REPO, generation_id=GEN, path="README.md"),
        ]
    return RAGResponse(
        answer="It does X.",
        sources=["pkg/mod.py"],
        repo_id=REPO,
        retrieval_plan={},
        model_used="m1",
        trace_id="t1",
        envelope=EvidenceEnvelope(
            repo_id=REPO, generation_id=generation, commit_sha="a" * 40
        )
        if envelope
        else None,
        citations=citations,
    )


class Harness:
    def __init__(self, monkeypatch, generations, result=None, rag_error=None):
        self.generations = list(generations)
        self.rag_calls = 0
        self.result = result or _result()
        self.rag_error = rag_error

        async def current(repo_id):
            value = (
                self.generations.pop(0)
                if len(self.generations) > 1
                else (self.generations[0])
            )
            if isinstance(value, Exception):
                raise value
            return value

        async def run(query):
            self.rag_calls += 1
            self.query = query
            if self.rag_error:
                raise self.rag_error
            return self.result

        monkeypatch.setattr(product_routes, "_current_generation", current)
        monkeypatch.setattr(product_routes, "_run_standard_rag", run)
        self.client = TestClient(app)

    def ask(self, **overrides):
        body = {"question": "What does it do?", "generation_id": GEN, **overrides}
        return self.client.post(URL, json=body)


def _error(response, code, status):
    assert response.status_code == status, response.text
    assert response.json()["error"]["code"] == code


def test_successful_ask_has_mode_run_id_envelope_and_citations(monkeypatch):
    h = Harness(monkeypatch, [GEN])
    body = h.ask().json()
    assert body["mode"] == "ask" and body["run_id"]
    assert body["generation_id"] == GEN and body["answer"] == "It does X."
    assert body["envelope"]["commit_sha"] == "a" * 40
    ranged, unranged = body["citations"]
    assert (ranged["start_line"], ranged["end_line"]) == (1, 3)
    assert unranged["start_line"] is None and unranged["range_reason"]
    assert "retrieval_plan" not in body
    assert h.query.execution_mode == "rag" and h.query.repo_id == REPO


def test_run_ids_are_distinct(monkeypatch):
    h = Harness(monkeypatch, [GEN])
    assert h.ask().json()["run_id"] != h.ask().json()["run_id"]


def test_stale_before_dispatch_runs_nothing(monkeypatch):
    h = Harness(monkeypatch, [OTHER])
    response = h.ask()
    _error(response, "stale", 409)
    assert response.json()["error"]["details"]["current_generation_id"] == OTHER
    assert h.rag_calls == 0


def test_generation_changing_during_call_is_not_published(monkeypatch):
    h = Harness(monkeypatch, [GEN, OTHER])
    response = h.ask()
    _error(response, "stale", 409)
    assert "It does X." not in response.text
    assert h.rag_calls == 1


def test_answer_from_another_generation_is_rejected(monkeypatch):
    h = Harness(monkeypatch, [GEN], result=_result(generation=OTHER))
    _error(h.ask(), "stale", 409)


def test_missing_envelope_is_rejected(monkeypatch):
    h = Harness(monkeypatch, [GEN], result=_result(envelope=False))
    _error(h.ask(), "stale", 409)


@pytest.mark.parametrize(
    "citation",
    [
        Citation(repo_id=REPO, generation_id=OTHER, path="a.py"),
        Citation(repo_id=OTHER, generation_id=GEN, path="a.py"),
        Citation(repo_id=REPO, generation_id=None, path="a.py"),
    ],
)
def test_citations_outside_scope_are_rejected(monkeypatch, citation):
    h = Harness(monkeypatch, [GEN], result=_result(citations=[citation]))
    response = h.ask()
    _error(response, "unavailable", 503)
    assert "It does X." not in response.text


def test_pipeline_conflict_maps_to_stale(monkeypatch):
    h = Harness(
        monkeypatch,
        [GEN],
        rag_error=HTTPException(409, "Repository generation changed; retry"),
    )
    _error(h.ask(), "stale", 409)


def test_repository_not_ready_is_unavailable(monkeypatch):
    h = Harness(monkeypatch, [HTTPException(503, "Repository is not ready; retry")])
    _error(h.ask(), "unavailable", 503)
    assert h.rag_calls == 0


def test_pipeline_failure_is_a_stable_error(monkeypatch):
    h = Harness(monkeypatch, [GEN], rag_error=HTTPException(500, "boom"))
    _error(h.ask(), "unavailable", 503)


@pytest.mark.parametrize(
    "overrides",
    [{"question": ""}, {"question": "x" * 8193}, {"top_k": 0}, {"top_k": 21}],
)
def test_invalid_request_bodies_are_rejected(monkeypatch, overrides):
    h = Harness(monkeypatch, [GEN])
    assert h.ask(**overrides).status_code == 422
    assert h.rag_calls == 0


def test_non_uuid_generation_is_invalid_request(monkeypatch):
    h = Harness(monkeypatch, [GEN])
    _error(h.ask(generation_id="nope"), "invalid_request", 400)
    assert h.rag_calls == 0


def test_existing_rag_route_has_no_generation_field():
    # The legacy contract is unchanged: no expected-generation field was added.
    from src.api.v1.models import RAGQuery

    assert "generation_id" not in RAGQuery.model_fields


def test_standard_rag_result_model_is_coerced_not_asserted(monkeypatch):
    """Found by the #440 live run: the pipeline returns its own RAGResult, not
    RAGResponse. The helper must accept it (FastAPI's response_model does that
    coercion only on the legacy route)."""
    import asyncio

    from src.api.v1 import routes
    from src.api.v1.models import RAGQuery, RAGResponse
    from src.core.service import RAGResult

    pipeline_result = RAGResult(
        answer="coerced",
        sources=["pkg/mod.py"],
        repo_id=REPO,
        retrieval_plan={"generation_id": GEN},
        model_used="m1",
        envelope=EvidenceEnvelope(repo_id=REPO, generation_id=GEN),
        citations=[Citation(repo_id=REPO, generation_id=GEN, path="pkg/mod.py")],
    )

    async def fake_endpoint(query):
        return pipeline_result

    monkeypatch.setattr(routes, "rag_endpoint", fake_endpoint)
    result = asyncio.run(
        product_routes._run_standard_rag(RAGQuery(query="q", repo_id=REPO))
    )
    assert isinstance(result, RAGResponse) and not isinstance(result, RAGResult)
    assert result.answer == "coerced" and result.model_used == "m1"
    assert result.citations[0].path == "pkg/mod.py"
    assert result.envelope.generation_id == GEN


def test_unexpected_pipeline_exception_still_returns_the_stable_error(monkeypatch):
    h = Harness(
        monkeypatch, [GEN], rag_error=RuntimeError("boom: /srv/private/path.py")
    )
    response = h.ask()
    _error(response, "unavailable", 503)
    assert "boom" not in response.text and "private" not in response.text
