# shared/embedders/factory.py
from shared.embedders.mock import MockEmbedder
from shared.embedders.ollama import OllamaEmbedder


def get_embedder(
    *,
    provider: str,
    ollama_base_url: str | None = None,
    ollama_model: str | None = None,
    ollama_batch_size: int = 50,
):
    if provider == "ollama":
        if not ollama_base_url or not ollama_model:
            raise ValueError("Ollama config required for ollama embedder")

        return OllamaEmbedder(
            base_url=ollama_base_url,
            model=ollama_model,
            batch_size=ollama_batch_size,
        )

    if provider == "mock":
        return MockEmbedder()

    raise ValueError(f"Unknown embedder provider: {provider}")
