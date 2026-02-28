# ingestion_service/src/core/embedders/factory.py
from shared.embedders.mock import MockEmbedder
from shared.embedders.ollama import OllamaEmbedder
from src.core.config import get_settings
import logging

logging.basicConfig(level=logging.DEBUG)


def get_embedder(provider: str | None = None):
    """
    Return an embedder based on provider name.

    - If provider is "ollama", returns OllamaEmbedder
    - Otherwise, returns MockEmbedder
    """
    logging.debug("get_embedder provider %s", provider)
    settings = get_settings()
    # Ensure provider is a string
    provider_str: str = (
        provider if provider is not None else settings.EMBEDDING_PROVIDER
    )
    VALID_PROVIDERS = {"ollama", "mock"}

    if provider_str == "ollama":
        logging.debug("settings.OLLAMA_BASE_URL : %s", settings.OLLAMA_BASE_URL)
        logging.debug("settings.OLLAMA_EMBED_MODEL : %s", settings.OLLAMA_EMBED_MODEL)
        return OllamaEmbedder(
            base_url=settings.OLLAMA_BASE_URL,
            model=settings.OLLAMA_EMBED_MODEL,
            batch_size=settings.OLLAMA_BATCH_SIZE,
        )
    elif provider_str == "mock":  # ← EXPLICIT
        return MockEmbedder()
    else:
        raise ValueError(
            f"Unknown embedder provider: '{provider_str}'.\
                          Valid: {VALID_PROVIDERS}"
        )
