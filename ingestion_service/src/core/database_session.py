# ingestion_service/src/core/database_session.py
from sqlalchemy import create_engine
from sqlalchemy.engine import Engine
from sqlalchemy.orm import sessionmaker, Session
from contextlib import contextmanager
from typing import Iterator, Optional, cast
from src.core.config import get_settings

_engine: Optional[Engine] = None
_SessionLocal = None


def get_engine() -> Engine:
    global _engine
    if _engine is None:
        settings = get_settings()
        # Bound connection establishment too: statement_timeout only starts
        # protecting an export after a connection has been acquired.
        _engine = cast(Engine, create_engine(
            settings.DATABASE_URL, echo=False, connect_args={"connect_timeout": 5},
        ))
    return _engine


def get_sessionmaker() -> sessionmaker:
    global _SessionLocal
    if _SessionLocal is None:
        _SessionLocal = sessionmaker(
            bind=get_engine(),
            autocommit=False,
            autoflush=False,
        )
    return _SessionLocal


# ----------------------------
# Add this
# ----------------------------
def get_db() -> Iterator[Session]:
    """
    FastAPI dependency: yields a SQLAlchemy session and ensures it is closed.
    """
    SessionLocal = get_sessionmaker()
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


@contextmanager
def read_snapshot(session_factory=None):
    """CI-01: a fresh read-only snapshot, never a writer's active session.

    Isolation is set before autobegin emits data SQL. Rollback avoids ORM
    expiration/reloads and resets transaction-local settings on pooled connections.
    Callers must return materialized values, never ORM instances.
    """
    factory = session_factory or get_sessionmaker()
    with factory() as session:
        try:
            session.connection(
                execution_options={
                    "isolation_level": "REPEATABLE READ",
                    "postgresql_readonly": True,
                }
            )
            yield session
        finally:
            session.rollback()
