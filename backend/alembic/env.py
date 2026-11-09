"""Alembic environment. Uses the migrator role (MIGRATION_DATABASE_URL); the runtime role cannot create tables."""

import os

from alembic import context
from sqlalchemy import create_engine

from app.config import _normalise_url
from app.models import Base

target_metadata = Base.metadata


def _url() -> str:
    url = context.config.get_main_option("sqlalchemy.url") or os.environ.get("MIGRATION_DATABASE_URL") or os.environ.get("DATABASE_URL", "")
    if not url:
        raise SystemExit("Set MIGRATION_DATABASE_URL (or DATABASE_URL) before running migrations.")
    return _normalise_url(url)


with create_engine(_url()).connect() as connection:
    context.configure(connection=connection, target_metadata=target_metadata)
    with context.begin_transaction():
        context.run_migrations()
