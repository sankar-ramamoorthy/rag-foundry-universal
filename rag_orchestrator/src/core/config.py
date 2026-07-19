# rag_orchestrator/src/core/config.py
from __future__ import annotations

from functools import lru_cache
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    # -------------------------------------------------
    # Embedding configuration
    # -------------------------------------------------
    EMBEDDING_PROVIDER: str = "ollama"
    OLLAMA_BASE_URL: str = "http://host.docker.internal:11434"
    #OLLAMA_EMBED_MODEL: str = "nomic-embed-text:v1.5"
    OLLAMA_EMBED_MODEL: str = "mxbai-embed-large:latest"

    OLLAMA_BATCH_SIZE: int = 50

    # -------------------------------------------------
    # Retrieval expansion limits (issue #30 Part 3)
    # -------------------------------------------------
    # Cap on graph-expanded documents fetched per query; ranked expanded
    # docs beyond this are reported as considered-but-unused.
    MAX_EXPANDED_DOCS: int = 20
    # Chunks fetched per expanded doc — expansion is context, not the
    # primary hit, so this stays well below the seed top_k.
    EXPANDED_DOC_CHUNKS: int = 3
    # Overall chunk cap handed to the agent adapter (was 9999).
    MAX_TOTAL_CHUNKS: int = 50
    # Concurrency of search-by-doc fetches for expanded docs.
    MAX_CONCURRENT_DOC_FETCHES: int = 8

    # -------------------------------------------------
    # Service URLs (Docker service names)
    # -------------------------------------------------
    VECTOR_STORE_URL: str = "http://vector_store_service:8002"
    LLM_SERVICE_URL: str = "http://llm_service:8000"
    INGESTION_SERVICE_URL: str = "http://ingestion_service:8000"

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
    )


@lru_cache
def get_settings() -> Settings:
    """Returns cached application settings."""
    return Settings()


def reset_settings_cache():
    """Clear cached settings for testing or reload."""
    get_settings.cache_clear()
