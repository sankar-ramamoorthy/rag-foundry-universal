# tests/api/test_health_endpoint.py
# Health endpoint (cheap regression guard)

from fastapi.testclient import TestClient
from src.api.v1.main import app

client = TestClient(app)

def test_health():
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json()["status"] == "ok"

