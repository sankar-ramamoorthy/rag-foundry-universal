"""Opt-in structured answers cross the actual /v1/rag HTTP route."""

from concurrent.futures import ThreadPoolExecutor
from itertools import product

import httpx
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from src.api.v1 import routes
from src.core import service

pytestmark = pytest.mark.unit
ORIGINAL_ASYNC_CLIENT = httpx.AsyncClient

INVENTORY = {
    "repo_id": "r1",
    "ingestion_id": "g1",
    "generation_status": "ready",
    "commit_sha": "a" * 40,
    "services": [
        {"name": "app", "compose_file": "docker-compose.yml",
         "dockerfile": "app/Dockerfile"},
        {"name": "postgres", "compose_file": "docker-compose.yml",
         "dockerfile": None},
    ],
    "manifests": [
        {"kind": "pyproject.toml", "path": "pyproject.toml"},
        {"kind": "Cargo.toml", "path": "tests/fixtures/crate/Cargo.toml"},
    ],
    "test_dirs": ["tests"],
    "file_counts": {"indexed": 2, "non_indexed": 1, "total": 3},
    "languages": {"python": 1, "markdown": 1, "rust": 1},
    "docs_dirs": ["DOCS"],
    "heuristic_fields": ["docs_dirs", "test_dirs"],
    "gaps": [{"category": "compose_parse", "path": "docker-compose.prod.yml",
              "reason": "unsupported YAML tag"}],
}
GRAPH = {
    "generation_status": "ready",
    "nodes": [
        {"relative_path": "app/src/main.py", "doc_type": "python source"},
        {"relative_path": "docker-compose.yml", "doc_type": "file"},
    ],
    "relationships": {},
}
COMPOSE = {
    "services": {
        "app": {
            "build": {"dockerfile": "app/Dockerfile"},
            "environment": {"DATABASE_URL": "postgresql://db@postgres:5432/app"},
            "depends_on": ["postgres"],
        },
        "postgres": {"image": "postgres:16", "ports": ["5434:5432"]},
    }
}


def _client(  # noqa: C901 - one HTTP backend models all route dependencies
    monkeypatch, *, enabled=True, snapshot_status=200, stale=False,
    snapshot_commit="a" * 40, snapshot_documents=None,
):
    settings = service.get_settings().model_copy(
        update={
            "REPOSITORY_OVERVIEW_STRUCTURED_ANSWERS_ENABLED": enabled,
            "REPOSITORY_OVERVIEW_CLAIM_SELECTION_ENABLED": False,
            "REPOSITORY_OVERVIEW_CANONICAL_SELECTION_ENABLED": False,
        }
    )
    monkeypatch.setattr(service, "get_settings", lambda: settings)
    monkeypatch.setattr(service, "get_embedder", lambda **_: object())
    monkeypatch.setattr(service, "embed_query", lambda *_: [0.1])

    async def resolve(repo_id):
        return repo_id

    async def retrieve(*_, **__):
        return {}, {
            "seed_document_ids": [],
            "expanded_document_ids": [],
            "expansion_metadata": {},
            "generation_id": "g1",
        }

    monkeypatch.setattr(service, "resolve_repo_id_http", resolve)
    monkeypatch.setattr(service, "hybrid_retrieve", retrieve)
    calls = []

    def backend(request):
        path = request.url.path
        calls.append(path)
        if path.endswith("/generation"):
            return httpx.Response(200, json={
                "ingestion_id": "g2" if stale else "g1",
                "generation_status": "ready",
            })
        if path.endswith("/orient"):
            return httpx.Response(200, json=INVENTORY)
        if path.endswith("/graph/repos/r1"):
            return httpx.Response(200, json=GRAPH)
        if path.endswith("/compose-snapshot"):
            if snapshot_status != 200:
                return httpx.Response(snapshot_status)
            documents = snapshot_documents
            if documents is None:
                documents = {
                    "docker-compose.yml": {
                        "sha256": "b" * 64, "content": COMPOSE,
                    }
                }
            return httpx.Response(200, json={
                "ingestion_id": "g1", "commit_sha": snapshot_commit,
                "compose_documents": documents,
            })
        if path == "/generate":
            return httpx.Response(200, json={"response": "model answer"})
        return httpx.Response(404)

    monkeypatch.setattr(
        httpx, "AsyncClient",
        lambda **kw: ORIGINAL_ASYNC_CLIENT(
            **kw, transport=httpx.MockTransport(backend)
        ),
    )
    app = FastAPI()
    app.include_router(routes.router, prefix="/v1")
    return TestClient(app), calls


@pytest.mark.parametrize("question,focus", [
    (
        "Describe the actual directory, service, and package structure "
        "of this repository.", "q2",
    ),
    (
        "Describe the actual directory, service, and package structure "
        "of rag-foundry-universal.", "q3",
    ),
    ("Give me an architectural map of this repository.", "q4"),
])
def test_structured_answer_http_uses_validated_facts(monkeypatch, question, focus):
    client, calls = _client(monkeypatch)
    response = client.post("/v1/rag", json={
        "query": question, "repo_id": "r1", "claim_type": "repository_overview",
    })
    assert response.status_code == 200, response.text
    result = response.json()
    assert result["retrieval_plan"]["structured_answer"]["focus"] == focus
    assert result["retrieval_plan"]["structured_answer"]["validation_errors"] == []
    assert "docker-compose.yml" in result["sources"]
    assert any(
        path.endswith("/orient")
        for path in result["retrieval_plan"]["structured_answer"]["evidence_apis"]
    )
    assert "/generate" not in calls
    if focus == "q3":
        assert "absence is not proven" in result["answer"]
        assert "Selected repository: r1" in result["answer"]
        assert "Dockerfiles" in result["answer"]
    if focus == "q4":
        assert "postgres: 5434:5432" in result["answer"]
        assert "DATABASE_URL, not HTTP" in result["answer"]
        assert "docker-compose.yml" in result["sources"]


def test_q1_reports_complete_pinned_orient_inventory_without_generation(monkeypatch):
    client, calls = _client(monkeypatch)
    response = client.post("/v1/rag", json={
        "query": "I need information about the repo structure.",
        "repo_id": "r1", "claim_type": "repository_overview",
    })
    assert response.status_code == 200, response.text
    result = response.json()
    structured = result["retrieval_plan"]["structured_answer"]
    assert structured["focus"] == "q1"
    assert structured["validation_errors"] == []
    assert structured["result"]["language_counts"] == INVENTORY["languages"]
    assert structured["result"]["manifests"] == INVENTORY["manifests"]
    for language, count in INVENTORY["languages"].items():
        assert f"{language}: {count}" in result["answer"]
    for manifest in INVENTORY["manifests"]:
        assert manifest["path"] in result["answer"]
    assert "indexed: 2" in result["answer"]
    assert "non_indexed: 1" in result["answer"]
    assert "tests" in result["answer"]
    assert "DOCS" in result["answer"]
    assert "docker-compose.prod.yml" in result["answer"]
    assert "heuristic" in result["answer"].lower()
    assert "docker-compose.yml" in result["sources"]
    assert "pyproject.toml" in result["sources"]
    assert "/generate" not in calls
    assert "/v1/graph/repos/r1" not in calls


def test_q1_stale_generation_fails_closed(monkeypatch):
    client, calls = _client(monkeypatch, stale=True)
    response = client.post("/v1/rag", json={
        "query": "I need information about the repo structure.",
        "repo_id": "r1", "claim_type": "repository_overview",
    })
    assert response.status_code == 409
    assert "/generate" not in calls


def test_q1_incomplete_inventory_fails_closed(monkeypatch):
    monkeypatch.delitem(INVENTORY, "languages")
    client, calls = _client(monkeypatch)
    response = client.post("/v1/rag", json={
        "query": "I need information about the repo structure.",
        "repo_id": "r1", "claim_type": "repository_overview",
    })
    assert response.status_code == 503
    assert "/generate" not in calls


def test_q1_default_off_keeps_generation_path(monkeypatch):
    client, calls = _client(monkeypatch, enabled=False)
    response = client.post("/v1/rag", json={
        "query": "I need information about the repo structure.",
        "repo_id": "r1", "claim_type": "repository_overview",
    })
    assert response.status_code == 200, response.text
    assert response.json()["answer"] == "model answer"
    assert "structured_answer" not in response.json()["retrieval_plan"]
    assert "/generate" in calls


def test_snapshot_mismatch_and_missing_content_fail_closed(monkeypatch):
    question = "Give me an architectural map of this repository."
    client, calls = _client(monkeypatch, snapshot_status=409)
    result = client.post("/v1/rag", json={
        "query": question, "repo_id": "r1", "claim_type": "repository_overview",
    })
    assert result.status_code == 409
    assert "/generate" not in calls
    client, calls = _client(monkeypatch, snapshot_status=404)
    result = client.post("/v1/rag", json={
        "query": question, "repo_id": "r1", "claim_type": "repository_overview",
    })
    assert result.status_code == 503
    assert "/generate" not in calls


def test_generation_mismatch_fails_closed(monkeypatch):
    client, calls = _client(monkeypatch, stale=True)
    result = client.post("/v1/rag", json={
        "query": (
            "Describe the actual directory, service, and package structure "
            "of this repository."
        ),
        "repo_id": "r1", "claim_type": "repository_overview",
    })
    assert result.status_code == 409
    assert "/generate" not in calls


def test_unrelated_query_keeps_generation_path(monkeypatch):
    client, calls = _client(monkeypatch)
    result = client.post("/v1/rag", json={
        "query": "What does GraphAssembler.assemble do?", "repo_id": "r1",
        "claim_type": "repository_overview",
    })
    assert result.status_code == 200, result.text
    assert result.json()["answer"] == "model answer"
    assert "/generate" in calls


def test_default_off_keeps_q2_generation_path(monkeypatch):
    client, calls = _client(monkeypatch, enabled=False)
    result = client.post("/v1/rag", json={
        "query": (
            "Describe the actual directory, service, and package structure "
            "of this repository."
        ),
        "repo_id": "r1", "claim_type": "repository_overview",
    })
    assert result.status_code == 200, result.text
    assert result.json()["answer"] == "model answer"
    assert "structured_answer" not in result.json()["retrieval_plan"]
    assert "/generate" in calls


def test_snapshot_source_commit_mismatch_fails_closed(monkeypatch):
    client, calls = _client(monkeypatch, snapshot_commit="different")
    result = client.post("/v1/rag", json={
        "query": "Give me an architectural map of this repository.",
        "repo_id": "r1", "claim_type": "repository_overview",
    })
    assert result.status_code == 409
    assert "/generate" not in calls


def test_snapshot_missing_declared_compose_file_fails_closed(monkeypatch):
    client, calls = _client(monkeypatch, snapshot_documents={"other.yml": {
        "sha256": "b" * 64,
        "content": {"services": {"app": {"image": "busybox"}}},
    }})
    result = client.post("/v1/rag", json={
        "query": "Give me an architectural map of this repository.",
        "repo_id": "r1", "claim_type": "repository_overview",
    })
    assert result.status_code == 503
    assert "/generate" not in calls


def test_request_can_enable_structured_answers_without_server_flag(monkeypatch):
    client, calls = _client(monkeypatch, enabled=False)
    result = client.post("/v1/rag", json={
        "query": "I need information about the repo structure.",
        "repo_id": "r1", "claim_type": "repository_overview",
        "repository_overview_structured_answers_enabled": True,
    })
    assert result.status_code == 200, result.text
    plan = result.json()["retrieval_plan"]
    assert plan["structured_answer"]["focus"] == "q1"
    assert plan["repository_overview_controls"] == {
        "claim_type": "repository_overview", "active": True,
        "claim_selection_enabled": False,
        "structured_answers_enabled": True,
        "canonical_selection_enabled": False,
    }
    assert "/generate" not in calls


def test_request_can_disable_enabled_server_default(monkeypatch):
    client, calls = _client(monkeypatch, enabled=True)
    result = client.post("/v1/rag", json={
        "query": "I need information about the repo structure.",
        "repo_id": "r1", "claim_type": "repository_overview",
        "repository_overview_structured_answers_enabled": False,
    })
    assert result.status_code == 200, result.text
    assert "structured_answer" not in result.json()["retrieval_plan"]
    assert not result.json()["retrieval_plan"]["repository_overview_controls"][
        "structured_answers_enabled"
    ]
    assert "/generate" in calls


def test_omitted_overrides_preserve_existing_defaults(monkeypatch):
    client, _ = _client(monkeypatch, enabled=True)
    result = client.post("/v1/rag", json={
        "query": "I need information about the repo structure.",
        "repo_id": "r1", "claim_type": "repository_overview",
    })
    assert result.status_code == 200, result.text
    controls = result.json()["retrieval_plan"]["repository_overview_controls"]
    assert controls["structured_answers_enabled"] is True
    assert controls["claim_selection_enabled"] is False
    assert controls["canonical_selection_enabled"] is False
    assert result.json()["retrieval_plan"]["structured_answer"]["focus"] == "q1"


@pytest.mark.parametrize(
    "claim,structured,canonical", list(product((False, True), repeat=3))
)
def test_independent_request_controls(monkeypatch, claim, structured, canonical):
    client, _ = _client(monkeypatch, enabled=False)
    selected = []

    async def select(chunks, _query, _repo, _generation, _embedding,
                     _per_doc, _total, claim_enabled, canonical_enabled):
        selected.append((claim_enabled, canonical_enabled))
        return chunks, set(), "current_structure", {}

    monkeypatch.setattr(service, "_apply_overview_selection", select)
    result = client.post("/v1/rag", json={
        "query": "I need information about the repo structure.",
        "repo_id": "r1", "claim_type": "repository_overview",
        "repository_overview_claim_selection_enabled": claim,
        "repository_overview_structured_answers_enabled": structured,
        "repository_overview_canonical_selection_enabled": canonical,
    })
    assert result.status_code == 200, result.text
    controls = result.json()["retrieval_plan"]["repository_overview_controls"]
    assert selected == [(claim, canonical)]
    assert controls["claim_selection_enabled"] is claim
    assert controls["structured_answers_enabled"] is structured
    assert controls["canonical_selection_enabled"] is canonical
    assert ("structured_answer" in result.json()["retrieval_plan"]) is structured


def test_exact_frozen_candidate_combination(monkeypatch):
    client, _ = _client(monkeypatch, enabled=False)

    async def no_extra_chunk(*_args):
        return None, []

    monkeypatch.setattr(service, "_fetch_canonical_overview_chunks", no_extra_chunk)
    result = client.post("/v1/rag", json={
        "query": "Describe the actual directory, service, and package "
                 "structure of this repository.",
        "repo_id": "r1", "claim_type": "repository_overview",
        "repository_overview_claim_selection_enabled": True,
        "repository_overview_structured_answers_enabled": True,
        "repository_overview_canonical_selection_enabled": False,
    })
    assert result.status_code == 200, result.text
    plan = result.json()["retrieval_plan"]
    assert plan["structured_answer"]["focus"] == "q2"
    assert plan["repository_overview_controls"]["claim_selection_enabled"]
    assert plan["repository_overview_controls"]["structured_answers_enabled"]
    assert not plan["repository_overview_controls"]["canonical_selection_enabled"]


@pytest.mark.parametrize("field", [
    "repository_overview_claim_selection_enabled",
    "repository_overview_structured_answers_enabled",
    "repository_overview_canonical_selection_enabled",
])
@pytest.mark.parametrize("value", ["true", 1, []])
def test_request_overrides_require_json_booleans(monkeypatch, field, value):
    client, _ = _client(monkeypatch, enabled=False)
    result = client.post("/v1/rag", json={
        "query": "q", "repo_id": "r1", field: value,
    })
    assert result.status_code == 422


def test_normal_query_does_not_activate_overview_controls(monkeypatch):
    client, calls = _client(monkeypatch, enabled=False)
    result = client.post("/v1/rag", json={
        "query": "ordinary question", "repo_id": "r1",
        "repository_overview_claim_selection_enabled": True,
        "repository_overview_structured_answers_enabled": True,
        "repository_overview_canonical_selection_enabled": True,
    })
    assert result.status_code == 200, result.text
    plan = result.json()["retrieval_plan"]
    assert not plan["repository_overview_controls"]["active"]
    assert "structured_answer" not in plan
    assert "/generate" in calls


def test_concurrent_requests_keep_overrides_isolated(monkeypatch):
    client, _ = _client(monkeypatch, enabled=False)
    question = "I need information about the repo structure."

    def ask(enabled):
        response = client.post("/v1/rag", json={
            "query": question, "repo_id": "r1",
            "claim_type": "repository_overview",
            "repository_overview_structured_answers_enabled": enabled,
        })
        assert response.status_code == 200, response.text
        return response.json()["retrieval_plan"]

    with ThreadPoolExecutor(max_workers=2) as pool:
        plans = list(pool.map(ask, (True, False)))
    assert "structured_answer" in plans[0]
    assert "structured_answer" not in plans[1]
    assert plans[0]["repository_overview_controls"]["structured_answers_enabled"]
    assert not plans[1]["repository_overview_controls"]["structured_answers_enabled"]
    assert not service.get_settings().REPOSITORY_OVERVIEW_STRUCTURED_ANSWERS_ENABLED
