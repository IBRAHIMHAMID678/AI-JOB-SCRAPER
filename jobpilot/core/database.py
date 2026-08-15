"""
Database engine, session factory, and base class.
Uses SQLite by default; swap DATABASE_URL to PostgreSQL for production.
"""
from __future__ import annotations

from contextlib import contextmanager
from typing import Generator

from sqlalchemy import create_engine, event as sa_event
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

from .config import settings


class Base(DeclarativeBase):
    pass


def _make_engine():
    url = settings.DATABASE_URL
    kwargs: dict = {}
    if url.startswith("sqlite"):
        # SQLite needs check_same_thread=False for multi-threaded FastAPI
        kwargs["connect_args"] = {"check_same_thread": False}
    else:
        kwargs["pool_size"] = settings.DATABASE_POOL_SIZE
        kwargs["pool_pre_ping"] = True

    engine = create_engine(url, echo=settings.DATABASE_ECHO, **kwargs)

    if url.startswith("sqlite"):
        # Enable WAL mode for better concurrent reads
        @sa_event.listens_for(engine, "connect")
        def _set_sqlite_pragma(dbapi_con, _):
            dbapi_con.execute("PRAGMA journal_mode=WAL")
            dbapi_con.execute("PRAGMA foreign_keys=ON")

    return engine


engine = _make_engine()

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


def init_db() -> None:
    """Create all tables. Call once at startup."""
    from . import models  # noqa: F401 — ensure models are registered
    Base.metadata.create_all(bind=engine)


def get_db() -> Generator[Session, None, None]:
    """FastAPI dependency — yields a DB session."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


@contextmanager
def db_session() -> Generator[Session, None, None]:
    """Context manager for use outside FastAPI (workers, agents)."""
    db = SessionLocal()
    try:
        yield db
        db.commit()
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()
