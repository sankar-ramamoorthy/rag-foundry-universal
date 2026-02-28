# vector_store_service/src/core/config.py
from functools import lru_cache
import os

from pydantic_settings import BaseSettings, SettingsConfigDict

from src.core.vectorstore.pgvector_store import PgVectorStore


class Settings(BaseSettings):
    DATABASE_URL: str
    EMBEDDING_PROVIDER: str = "mock"
    OLLAMA_BASE_URL: str = "http://host.docker.internal:11434"
    OLLAMA_EMBED_MODEL: str = "nomic-embed-text:v1.5"
    OLLAMA_BATCH_SIZE: int = 50

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
    )


@lru_cache()
def get_settings() -> Settings:
    """Load and cache settings from environment."""
    return Settings()


@lru_cache()
def get_vector_store() -> PgVectorStore:
    """Dependency that provides the vector store instance."""
    settings = get_settings()

    dsn = settings.DATABASE_URL
    dimension = int(os.getenv("VECTOR_DIMENSION", "768"))
    provider = settings.EMBEDDING_PROVIDER

    return PgVectorStore(
        dsn=dsn,
        dimension=dimension,
        provider=provider,
    )
