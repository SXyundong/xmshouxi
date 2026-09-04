"""SQLAlchemy engine and request-scoped session helpers."""

from collections.abc import Generator
import os

from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from app.config import settings

engine = create_engine(
    settings.DATABASE_URL,
    echo=settings.DB_ECHO,
    pool_pre_ping=True,
    # Railway's small PostgreSQL plans expose a low connection ceiling. Keep
    # the web service from opening an unbounded pool so one-off sync jobs can
    # still obtain a connection.
    pool_size=int(os.getenv("DB_POOL_SIZE", "1")),
    max_overflow=int(os.getenv("DB_MAX_OVERFLOW", "0")),
    pool_timeout=int(os.getenv("DB_POOL_TIMEOUT", "30")),
)
SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False, expire_on_commit=False)


def get_db() -> Generator[Session, None, None]:
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
