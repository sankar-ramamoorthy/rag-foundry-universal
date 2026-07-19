# llm_service/tests/api/test_models_endpoint.py
"""
WP-M5: GET /v1/models lists aliases and marks the default.
"""
from fastapi.testclient import TestClient

from src.api.v1.main import app

client = TestClient(app)


def test_models_endpoint_lists_aliases_with_default():
    response = client.get("/v1/models")

    assert response.status_code == 200
    body = response.json()
    assert body["default"] == "default"

    by_alias = {m["alias"]: m for m in body["models"]}
    assert by_alias["default"]["is_default"] is True
    # aliases shipped in llm_service/models.yaml
    assert "smart" in by_alias
    assert by_alias["smart"]["model"] == "anthropic/claude-sonnet-5"
    assert by_alias["smart"]["is_default"] is False


def test_summarize_forwards_model_alias(monkeypatch):
    """WP-M5: /v1/summarize honors the model param instead of the old
    hardcoded phi4-mini."""
    captured = {}

    async def fake_fetch_chunks(ingestion_id):
        return ["chunk text"]

    async def fake_update(ingestion_id, summary):
        return None

    async def fake_generate(**kwargs):
        captured.update(kwargs)
        return {"response": "a summary"}

    monkeypatch.setattr("src.api.v1.summarize.fetch_chunks", fake_fetch_chunks)
    monkeypatch.setattr(
        "src.api.v1.summarize.update_document_summary", fake_update
    )
    monkeypatch.setattr(
        "src.api.v1.summarize.generate_completion", fake_generate
    )

    response = client.post(
        "/v1/summarize/123e4567-e89b-12d3-a456-426614174000?model=smart"
    )

    assert response.status_code == 200
    assert captured["model"] == "smart"
    assert response.json()["summary"] == "a summary"
