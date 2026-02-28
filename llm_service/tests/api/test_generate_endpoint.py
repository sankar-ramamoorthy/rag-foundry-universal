# tests/api/test_generate_endpoint.py
# API endpoint tests (FastAPI boundary)
# This isolates:
# request validation
# response serialization
# error propagation

from fastapi.testclient import TestClient
from src.api.v1.main import app

client = TestClient(app)

def test_generate_endpoint_happy_path(monkeypatch):
    async def fake_generate(**kwargs):
        return {
            "provider": "ollama",
            "model": "x",
            "response": "answer"
        }

    monkeypatch.setattr(
        "src.api.v1.main.generate_completion",
        fake_generate,
    )

    response = client.post(
        "/generate",
        json={"context": "c", "query": "q"},
    )

    assert response.status_code == 200
    assert response.json()["response"] == "answer"
