# ingestion_service/src/core/config.py

from functools import lru_cache
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    DATABASE_URL: str
    VECTOR_STORE_SERVICE_URL: str = "http://vector_store_service:8002"
    EMBEDDING_PROVIDER: str = "ollama"
    OLLAMA_BASE_URL: str = "http://host.docker.internal:11434"

    # Coderag upgrade
    OLLAMA_EMBED_MODEL: str = "mxbai-embed-large:latest"
    OLLAMA_BATCH_SIZE: int = 50
    VECTOR_DIMENSION: int = 1024

    # Universal feature
    DOCLING_ENABLED: bool = True   # When False → PyMuPDF fallback for PDF

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
    )


@lru_cache
def get_settings() -> "Settings":
    return Settings()


def reset_settings_cache():
    get_settings.cache_clear()