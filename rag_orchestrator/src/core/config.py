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
    OLLAMA_EMBED_MODEL: str = "nomic-embed-text:v1.5"
    OLLAMA_BATCH_SIZE: int = 50

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
