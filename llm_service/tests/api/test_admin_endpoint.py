# llm_service/tests/api/test_admin_endpoint.py
"""
WP-M7: PUT/DELETE /v1/admin/policy/{slot} -- shared-secret write auth,
resolve()-only validation, runtime policy refresh with no restart.
"""
import httpx
import pytest
from fastapi.testclient import TestClient

from src.api.v1.main import app
from src.core.model_catalog import reset_catalog_cache
from src.core.model_policy import load_policy
from src.core.model_registry import reset_registry

client = TestClient(app)


@pytest.fixture(autouse=True)
def _no_real_network(monkeypatch):
    """GET /v1/models (hit inside several tests below) fans out to every
    endpoint/provider catalog -- keep that off the real network and fast
    (no multi-second timeouts) instead of leaving it unmocked."""

    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("unreachable")

    real_async_client = httpx.AsyncClient

    def patched_client(*args, **kwargs):
        kwargs["transport"] = httpx.MockTransport(handler)
        return real_async_client(*args, **kwargs)

    monkeypatch.setattr(httpx, "AsyncClient", patched_client)
    reset_catalog_cache()
    yield
    reset_catalog_cache()


@pytest.fixture()
def policy_path(tmp_path, monkeypatch):
    path = tmp_path / "model-policy.json"
    monkeypatch.setenv("MODEL_POLICY_PATH", str(path))
    reset_registry()
    yield path
    reset_registry()


def test_write_disabled_when_secret_unset(policy_path, monkeypatch):
    monkeypatch.delenv("LLM_ADMIN_SECRET", raising=False)
    response = client.put(
        "/v1/admin/policy/fast", json={"model": "groq/llama-3.1-8b-instant"}
    )
    assert response.status_code == 503
    assert load_policy()["slots"] == {}


def test_write_rejected_with_wrong_secret(policy_path, monkeypatch):
    monkeypatch.setenv("LLM_ADMIN_SECRET", "correct-secret")
    response = client.put(
        "/v1/admin/policy/fast",
        json={"model": "groq/llama-3.1-8b-instant"},
        headers={"X-Admin-Secret": "wrong"},
    )
    assert response.status_code == 401
    assert load_policy()["slots"] == {}


def test_write_rejected_with_missing_header(policy_path, monkeypatch):
    monkeypatch.setenv("LLM_ADMIN_SECRET", "correct-secret")
    response = client.put(
        "/v1/admin/policy/fast", json={"model": "groq/llama-3.1-8b-instant"}
    )
    assert response.status_code == 401


def test_valid_write_persists_and_hot_refreshes_with_no_restart(
    policy_path, monkeypatch
):
    monkeypatch.setenv("LLM_ADMIN_SECRET", "correct-secret")

    response = client.put(
        "/v1/admin/policy/fast",
        json={"model": "groq/llama-3.1-8b-instant"},
        headers={"X-Admin-Secret": "correct-secret"},
    )
    assert response.status_code == 200
    assert response.json()["model"] == "groq/llama-3.1-8b-instant"

    # same test process, no restart -- GET /v1/models already reflects it
    body = client.get("/v1/models").json()
    by_alias = {m["alias"]: m for m in body["models"]}
    assert by_alias["fast"]["model"] == "groq/llama-3.1-8b-instant"
    assert by_alias["fast"]["overridden_by_policy"] is True


def test_invalid_model_string_rejected_and_not_persisted(policy_path, monkeypatch):
    monkeypatch.setenv("LLM_ADMIN_SECRET", "correct-secret")
    response = client.put(
        "/v1/admin/policy/fast",
        json={"model": ""},
        headers={"X-Admin-Secret": "correct-secret"},
    )
    assert response.status_code == 400
    assert load_policy()["slots"] == {}


def test_clear_slot_removes_override(policy_path, monkeypatch):
    monkeypatch.setenv("LLM_ADMIN_SECRET", "correct-secret")
    headers = {"X-Admin-Secret": "correct-secret"}
    client.put(
        "/v1/admin/policy/fast",
        json={"model": "groq/llama-3.1-8b-instant"},
        headers=headers,
    )

    response = client.delete("/v1/admin/policy/fast", headers=headers)
    assert response.status_code == 200
    assert load_policy()["slots"] == {}

    body = client.get("/v1/models").json()
    by_alias = {m["alias"]: m for m in body["models"]}
    assert by_alias["fast"]["overridden_by_policy"] is False


def test_clear_requires_secret_too(policy_path, monkeypatch):
    monkeypatch.setenv("LLM_ADMIN_SECRET", "correct-secret")
    response = client.delete("/v1/admin/policy/fast")
    assert response.status_code == 401
