# ingestion_service/tests/api/test_graph_export_event_loop.py
"""
Issue #271: GET /v1/graph/repos/{repo_id} must not run the synchronous
full-graph DB export on the event loop.

The handler used to be `async def` with no `await`, so a multi-second export
blocked every other request to the (single-process) service, including
/version and health checks. A plain `def` handler runs in FastAPI's thread
pool instead. The export is stubbed with a blocking sleep so no database is
needed.
"""

import asyncio
import time
from types import SimpleNamespace

import httpx
import pytest
from fastapi import FastAPI

from src.api.v1 import graph as graph_module
from src.core import db_utils

pytestmark = pytest.mark.unit

EXPORT_SECONDS = 1.0
REPO_ID = "00000000-0000-4000-8000-000000000271"


def _node(canonical_id: str) -> SimpleNamespace:
    return SimpleNamespace(
        document_id=f"doc-{canonical_id}",
        canonical_id=canonical_id,
        relative_path="a.py",
        title=canonical_id,
        doc_type="function",
        provenance={"authority": "code"},
    )


def _graph_data() -> dict:
    return {
        "nodes": {"a.py#f": _node("a.py#f"), "a.py#g": _node("a.py#g")},
        "relationships": {
            "a.py#f": [
                {
                    "to_canonical_id": "a.py#g",
                    "relation_type": "CALLS",
                    "relationship_metadata": {"confidence": 0.9},
                }
            ]
        },
        "generation_status": "ready",
    }


def _app() -> FastAPI:
    app = FastAPI()
    app.include_router(graph_module.router, prefix="/v1")

    @app.get("/ping")
    async def ping():  # stands in for /version: needs the event loop
        return {"ok": True}

    return app


def _client(app: FastAPI) -> httpx.AsyncClient:
    return httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://test"
    )


def test_other_requests_are_served_while_an_export_runs(monkeypatch):
    def slow_export(repo_id: str) -> dict:
        time.sleep(EXPORT_SECONDS)  # synchronous, like the real DB export
        return _graph_data()

    monkeypatch.setattr(db_utils, "get_full_graph_for_repo", slow_export)

    async def scenario():
        async with _client(_app()) as client:
            export = asyncio.create_task(client.get(f"/v1/graph/repos/{REPO_ID}"))
            await asyncio.sleep(0.2)  # let the export start
            started = time.perf_counter()
            probe = await client.get("/ping")
            waited = time.perf_counter() - started
            export_done_during_probe = export.done()
            response = await export
            return probe, waited, export_done_during_probe, response

    probe, waited, export_done_during_probe, response = asyncio.run(scenario())

    assert probe.status_code == 200
    assert not export_done_during_probe, "probe must be served mid-export"
    assert waited < EXPORT_SECONDS / 2, (
        f"/ping waited {waited:.2f}s behind a {EXPORT_SECONDS}s export: "
        "the export is blocking the event loop"
    )
    assert response.status_code == 200


def test_export_response_contract_is_unchanged(monkeypatch):
    monkeypatch.setattr(
        db_utils, "get_full_graph_for_repo", lambda repo_id: _graph_data()
    )

    async def fetch():
        async with _client(_app()) as client:
            return await client.get(f"/v1/graph/repos/{REPO_ID}")

    body = asyncio.run(fetch()).json()

    assert set(body) == {"nodes", "relationships", "total_nodes", "generation_status"}
    assert body["total_nodes"] == 2
    assert body["generation_status"] == "ready"
    assert {n["canonical_id"] for n in body["nodes"]} == {"a.py#f", "a.py#g"}
    assert set(body["nodes"][0]) == {
        "document_id", "canonical_id", "relative_path", "title", "doc_type",
        "provenance",
    }
    assert body["relationships"] == {
        "a.py#f": [
            {
                "to_canonical_id": "a.py#g",
                "relation_type": "CALLS",
                "relationship_metadata": {"confidence": 0.9},
            }
        ]
    }
