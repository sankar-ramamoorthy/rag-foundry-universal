"""CI-01 / #335: real HTTP client/loader/cache composition."""

import copy
import json
from concurrent.futures import ThreadPoolExecutor
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from threading import Event, Thread
from urllib.parse import parse_qs, urlparse
from uuid import uuid4

import pytest
import requests

from src.retrieval import codebase_queries as queries, codebase_utils as cache

pytestmark = pytest.mark.unit
REPO = "ci01-fixture"
A, B = str(uuid4()), str(uuid4())


def envelope(generation=A):
    return {
        "repo_id": REPO,
        "ingestion_id": generation,
        "generation_status": "ready",
        "nodes": [
            {
                "canonical_id": "a.py#f",
                "document_id": "document-f",
                "relative_path": "a.py",
                "title": generation,
                "doc_type": "code",
            }
        ],
        "relationships": {},
        "total_nodes": 1,
    }


@pytest.fixture
def producer(monkeypatch):
    state = {
        "generation": A,
        "body": envelope(),
        "exports": 0,
        "lookups": 0,
        "status_code": 200,
        "expectations": [],
    }

    class Handler(BaseHTTPRequestHandler):
        def do_GET(self):
            path = urlparse(self.path)
            if path.path.endswith("/generation"):
                state["lookups"] += 1
                body = {
                    "repo_id": REPO,
                    "ingestion_id": state["generation"],
                    "generation_status": "ready",
                }
                status = 200
            else:
                state["exports"] += 1
                expected = parse_qs(path.query).get("expected_generation_id", [None])[0]
                state["expectations"].append(expected)
                body, status = copy.deepcopy(state["body"]), state["status_code"]
                if state.get("pause_first") and state["exports"] == 1:
                    state["reached"].set()
                    assert state["resume"].wait(10)
            self.send_response(status)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(json.dumps(body).encode())

        def log_message(self, format: str, *args) -> None:
            pass

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    thread = Thread(target=server.serve_forever, daemon=True)
    thread.start()
    monkeypatch.setattr(
        queries, "ingestion_service_url", f"http://127.0.0.1:{server.server_port}"
    )
    cache._repo_graphs.clear()
    try:
        yield state
    finally:
        if "resume" in state:
            state["resume"].set()
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)
        cache._repo_graphs.clear()


def test_cold_warm_force_reload_validate_actual_http(producer):
    generation, first = cache.get_cached_graph_with_generation(REPO)
    assert generation == first.ingestion_id == A
    assert cache.get_cached_graph_with_generation(REPO)[1] is first
    assert producer["exports"] == 1 and producer["lookups"] == 2
    assert (
        cache.get_cached_graph_with_generation(REPO, force_reload=True)[1] is not first
    )
    assert producer["exports"] == 2
    assert producer["expectations"] == [A, A]


@pytest.mark.parametrize(
    "fault",
    [
        "missing_identity",
        "wrong_identity",
        "wrong_repo",
        "missing_status",
        "building",
        "failed",
        "unknown",
        "wrong_count",
        "empty_ready",
        "bad_node",
        "duplicate_node",
        "bad_edges",
        "bad_metadata",
        "http_conflict",
        "http_error",
    ],
)
def test_invalid_or_unavailable_export_cannot_enter_cache(producer, fault):  # noqa: C901
    body = producer["body"]
    if fault == "missing_identity":
        body.pop("ingestion_id")
    elif fault == "wrong_identity":
        body["ingestion_id"] = B
    elif fault == "wrong_repo":
        body["repo_id"] = "other"
    elif fault == "missing_status":
        body.pop("generation_status")
    elif fault in ("building", "failed", "unknown"):
        body.update(
            generation_status=fault,
            ingestion_id=None,
            nodes=[],
            relationships={},
            total_nodes=0,
        )
    elif fault == "wrong_count":
        body["total_nodes"] = True  # bool must not pass as integer 1.
    elif fault == "empty_ready":
        body.update(nodes=[], total_nodes=0)
    elif fault == "bad_node":
        body["nodes"][0].pop("document_id")
    elif fault == "duplicate_node":
        body["nodes"].append(copy.deepcopy(body["nodes"][0]))
        body["total_nodes"] = 2
    elif fault == "bad_edges":
        body["relationships"] = {
            "a.py#f": [
                {
                    "to_canonical_id": "missing",
                    "relation_type": "CALL",
                    "relationship_metadata": {},
                }
            ]
        }
    elif fault == "bad_metadata":
        body["relationships"] = {
            "a.py#f": [
                {
                    "to_canonical_id": "a.py#f",
                    "relation_type": "CALL",
                    "relationship_metadata": [],
                }
            ]
        }
    else:
        producer["status_code"] = 409 if fault == "http_conflict" else 500
    with pytest.raises(queries.GraphSnapshotError):
        cache.get_cached_graph_with_generation(REPO)
    assert REPO not in cache._repo_graphs


def test_failed_freshness_check_never_falls_back_to_warm_graph(producer, monkeypatch):
    cache.get_cached_graph_with_generation(REPO)

    def fail(*args, **kwargs):
        raise requests.ConnectionError("injected")

    monkeypatch.setattr(queries.requests, "get", fail)
    with pytest.raises(queries.GraphSnapshotError) as exc:
        cache.get_cached_graph_with_generation(REPO)
    assert exc.value.status_code == 503
    assert producer["exports"] == 1


def test_concurrent_old_completion_cannot_bypass_next_freshness_check(producer):
    producer.update(pause_first=True, reached=Event(), resume=Event())
    with ThreadPoolExecutor() as pool:
        first = pool.submit(cache.get_cached_graph_with_generation, REPO)
        try:
            assert producer["reached"].wait(5)
            producer.update(generation=B, body=envelope(B))
            second_generation, second_graph = cache.get_cached_graph_with_generation(
                REPO,
                force_reload=True,
            )
            assert second_generation == second_graph.ingestion_id == B
        finally:
            producer["resume"].set()
        first_generation, first_graph = first.result(timeout=5)
    assert first_generation == first_graph.ingestion_id == A
    # Even if the older completion replaced the single cache slot, the next
    # fresh check sees B and forces a correctly fenced B reload.
    final_generation, final_graph = cache.get_cached_graph_with_generation(REPO)
    assert final_generation == final_graph.ingestion_id == B


@pytest.mark.parametrize(
    "body",
    [
        None,
        [],
        {},
        {"repo_id": "other"},
        {"repo_id": REPO, "generation_status": "ready", "ingestion_id": "invalid"},
        {"repo_id": REPO, "generation_status": "building", "ingestion_id": A},
    ],
)
def test_bad_lookup_cannot_authorize_reuse(monkeypatch, body):
    class Response:
        status_code = 200

        def json(self):
            return body

    monkeypatch.setattr(queries.requests, "get", lambda *a, **kw: Response())
    assert queries.get_repo_generation(REPO) == (None, "unknown")


@pytest.mark.parametrize("operation", ["trace", "impact"])
def test_structural_result_identity_and_unavailable_vs_absent(producer, operation):
    from fastapi.testclient import TestClient
    from src.api.v1.main import app

    client = TestClient(app)
    url = f"/v1/repos/{REPO}/{operation}"
    response = client.get(url, params={"start": "a.py#f"})
    assert response.status_code == 200
    assert response.json()["ingestion_id"] == A
    absent = client.get(url, params={"start": "not-present"})
    assert absent.status_code == 404
    assert absent.json()["detail"]["ingestion_id"] == A
    producer.update(
        generation=B,
        body={
            "repo_id": REPO,
            "generation_status": "building",
            "ingestion_id": None,
            "nodes": [],
            "relationships": {},
            "total_nodes": 0,
        },
    )
    unavailable = client.get(url, params={"start": "not-present"})
    assert unavailable.status_code == 503
