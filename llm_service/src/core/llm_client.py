import httpx

from src.core.config import (
    DEFAULT_LLM_PROVIDER,
    OLLAMA_BASE_URL,
    OLLAMA_MODEL,
)


async def generate_completion(
    *,
    context: str,
    query: str,
    provider: str | None = None,
    model: str | None = None,
) -> dict:
    active_provider = provider or DEFAULT_LLM_PROVIDER

    if active_provider == "ollama":
        active_model = model or OLLAMA_MODEL
    else:
        raise ValueError(f"Unsupported LLM provider: {active_provider}")

    prompt = f"Context:\n{context}\n\nQuestion:\n{query}"
    return_dict = {"provider": active_provider, "model": active_model, "response": ""}

    if active_provider == "ollama":
        async with httpx.AsyncClient( timeout=90) as client:
            response = await client.post(
                f"{OLLAMA_BASE_URL}/api/generate",
                json={"model": active_model, "prompt": prompt, "stream": False},
            )
            response.raise_for_status()
            answer = response.json().get("response", "").strip()
            return_dict = {
                "provider": active_provider,
                "model": active_model,
                "response": answer,
            }
    return return_dict
