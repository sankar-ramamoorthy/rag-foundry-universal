# tests/core/test_llm_client_prompt.py
# Purpose: Lock down the exact prompt contract.
# If someone “improves” the prompt later, this test will break by design.

import pytest
from src.core.llm_client import generate_completion

@pytest.mark.asyncio
async def test_prompt_construction(monkeypatch):
    captured_prompt = {}

    async def fake_post(self, url, json):
        captured_prompt["prompt"] = json["prompt"]

        class FakeResponse:
            def raise_for_status(self): pass
            def json(self):
                return {"response": "ok"}

        return FakeResponse()

    monkeypatch.setattr("httpx.AsyncClient.post", fake_post)

    await generate_completion(
        context="CTX",
        query="QUESTION",
        provider="ollama",
        model="test-model",
    )

    assert captured_prompt["prompt"] == (
        "Context:\nCTX\n\nQuestion:\nQUESTION"
    )
