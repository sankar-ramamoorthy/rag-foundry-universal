# tests/core/test_llm_client_http.py
# HTTP contract with Ollama (shape, not behavior)
# This ensures: correct endpoint , correct payload , 
#  no accidental streaming, stable output shape
#
import pytest
import respx
from httpx import Response
import json

from src.core.llm_client import generate_completion
from src.core.config import OLLAMA_BASE_URL

@pytest.mark.asyncio
@respx.mock
async def test_ollama_http_call():
    route = respx.post(f"{OLLAMA_BASE_URL}/api/generate").mock(
        return_value=Response(
            200,
            json={"response": "hello"}
        )
    )

    result = await generate_completion(
        context="ctx",
        query="q",
        provider="ollama",
        model="m",
    )

    assert route.called
    assert result["response"] == "hello"
    #request_json = route.calls[0].request.json()
    request = route.calls[0].request
    request_json = json.loads(request.content)    
    assert request_json["stream"] is False
    assert "prompt" in request_json
