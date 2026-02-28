# ingestion_service/src/core/config.py

from functools import lru_cache
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    DATABASE_URL: str
    VECTOR_STORE_SERVICE_URL: str = "http://vector_store_service:8002"
    EMBEDDING_PROVIDER: str = "ollama"
    OLLAMA_BASE_URL: str = "http://host.docker.internal:11434"
    OLLAMA_EMBED_MODEL: str = "nomic-embed-text:v1.5"
    OLLAMA_BATCH_SIZE: int = 50  # default batch size for Ollama embedding

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
    )


@lru_cache
def get_settings() -> Settings:
    """Returns cached application settings."""
    return Settings()  # type: ignore[reportCallIssue]


def reset_settings_cache():
    """Clear cached settings for testing or reload."""
    get_settings.cache_clear()
