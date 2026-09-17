# rag_orchestrator/tests/test_repo_generation_lookup.py
"""
Issue #168 (WP-R5): get_repo_generation is the cheap generation check the
graph cache uses instead of a full graph re-fetch on every call. A
freshness-check failure (network error, non-200) must degrade to "unknown"
rather than raise and take down the whole retrieval request.
"""
from dataclasses import dataclass
from typing import Any

import pytest
import requests

from src.retrieval import codebase_queries

pytestmark = pytest.mark.unit


@dataclass
class FakeResponse:
    status_code: int
    _body: Any = None
    text: str = ""

    def json(self):
        return self._body


def test_ready_generation_returns_ingestion_id_and_status(monkeypatch):
    monkeypatch.setattr(
        codebase_queries.requests, "get",
        lambda url, timeout=None: FakeResponse(
            200, {"repo_id": "repo-x", "ingestion_id": "ing-1",
                  "generation_status": "ready"},
        ),
    )

    ingestion_id, status = codebase_queries.get_repo_generation("repo-x")

    assert ingestion_id == "ing-1"
    assert status == "ready"


def test_building_generation_has_no_ingestion_id(monkeypatch):
    monkeypatch.setattr(
        codebase_queries.requests, "get",
        lambda url, timeout=None: FakeResponse(
            200, {"repo_id": "repo-x", "ingestion_id": None,
                  "generation_status": "building"},
        ),
    )

    ingestion_id, status = codebase_queries.get_repo_generation("repo-x")

    assert ingestion_id is None
    assert status == "building"


def test_non_200_response_degrades_to_unknown_not_an_exception(monkeypatch):
    monkeypatch.setattr(
        codebase_queries.requests, "get",
        lambda url, timeout=None: FakeResponse(500, text="db unavailable"),
    )

    ingestion_id, status = codebase_queries.get_repo_generation("repo-x")

    assert ingestion_id is None
    assert status == "unknown"


def test_network_error_degrades_to_unknown_not_an_exception(monkeypatch):
    def _raise(url, timeout=None):
        raise requests.ConnectionError("connection refused")

    monkeypatch.setattr(codebase_queries.requests, "get", _raise)

    ingestion_id, status = codebase_queries.get_repo_generation("repo-x")

    assert ingestion_id is None
    assert status == "unknown"
