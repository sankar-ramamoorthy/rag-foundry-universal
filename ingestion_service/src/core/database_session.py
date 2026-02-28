# ingestion_service/src/core/database_session.py
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, Session
from src.core.config import get_settings

_engine = None
_SessionLocal = None


def get_engine():
    global _engine
    if _engine is None:
        settings = get_settings()
        _engine = create_engine(settings.DATABASE_URL, echo=False)
    return _engine


def get_sessionmaker():
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
def get_db() -> Session:
    """
    FastAPI dependency: yields a SQLAlchemy session and ensures it is closed.
    """
    SessionLocal = get_sessionmaker()
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()