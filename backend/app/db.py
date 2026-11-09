"""Database engine and session dependency."""

from __future__ import annotations

from collections.abc import Iterator

from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

_engine = None
_factory: sessionmaker | None = None


def init_db(url: str) -> None:
    global _engine, _factory
    _engine = create_engine(url, pool_pre_ping=True, future=True)
    _factory = sessionmaker(_engine, expire_on_commit=False)


def get_engine():
    return _engine


def session() -> Session:
    """A session for code that runs outside a request dependency (use as a context manager)."""
    if _factory is None:
        raise RuntimeError("Database is not initialised.")
    return _factory()


def get_db() -> Iterator[Session]:
    if _factory is None:
        raise RuntimeError("Database is not initialised.")
    with _factory() as session:
        yield session
