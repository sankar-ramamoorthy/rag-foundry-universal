# ingestion_service/tests/conftest.py
"""
Pytest configuration for ingestion_service.

This file supports two testing modes:

- Unit tests (no DB, no Docker) → default CI behavior
- Integration tests (Docker + Postgres + pgvector + Ollama)

Integration tests are explicitly marked and skipped in CI.
"""

import sys
import pathlib
import os
import pytest

from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from src.core.database_session import get_sessionmaker

# ---------------------------------------------------------------------
# Path setup
# ---------------------------------------------------------------------
ROOT = pathlib.Path(__file__).parent.parent.resolve()  # ingestion_service/
SRC = ROOT / "src"
REPO_ROOT = ROOT.parent  # repo root

sys.path.insert(0, str(REPO_ROOT))  # allow `shared`
sys.path.insert(0, str(SRC))        # allow `ingestion_service.src`

# ---------------------------------------------------------------------
# Environment defaults (integration tests only)
# ---------------------------------------------------------------------
os.environ.setdefault(
    "DATABASE_URL",
    "postgresql://ingestion_user:ingestion_pass@postgres:5432/ingestion_test"
)
os.environ.setdefault("EMBEDDING_PROVIDER", "ollama")
os.environ.setdefault("OLLAMA_BASE_URL", "http://host.docker.internal:11434")
os.environ.setdefault("OLLAMA_EMBED_MODEL", "nomic-embed-text:15")

# ---------------------------------------------------------------------
# Database fixtures
# ---------------------------------------------------------------------

@pytest.fixture(scope="session")
def engine():
    """
    SQLAlchemy engine bound to the integration test database.

    Assumes:
    - Postgres + pgvector are running via Docker
    - Alembic migrations have already been applied
    """
    database_url = os.environ["DATABASE_URL"]
    engine = create_engine(database_url)
    return engine


@pytest.fixture(scope="session")
def session(engine) -> Session:
    """
    Shared SQLAlchemy session for integration tests.

    Note:
    - Session scope is intentional
    - Tests must be idempotent or use unique IDs
    """
    SessionLocal = get_sessionmaker()
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

# ---------------------------------------------------------------------
# Skip integration tests in CI
# ---------------------------------------------------------------------

def pytest_runtest_setup(item):
    if "integration" in item.keywords and os.environ.get("CI") == "true":
        pytest.skip(
            "Skipping integration tests in CI "
            "(requires Docker + Postgres + pgvector + Ollama)"
        )
