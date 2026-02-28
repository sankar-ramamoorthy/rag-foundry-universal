# tests/core/test_llm_client_provider.py
# Providor Validation
import pytest
from src.core.llm_client import generate_completion

@pytest.mark.asyncio
async def test_unsupported_provider_raises():
    with pytest.raises(ValueError, match="Unsupported LLM provider"):
        await generate_completion(
            context="x",
            query="y",
            provider="openai",
        )
