"""Alembic environment. Migrations run over the synchronous driver (the
same asyncpg->psycopg swap prefs.py does), both from the CLI (`alembic
upgrade head` in app/) and programmatically at app startup."""

import sys
from pathlib import Path

from alembic import context
from sqlalchemy import create_engine

# app/ on sys.path so config/models import when Alembic is run by the CLI.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from config import settings  # pylint: disable=wrong-import-position
from models import Base  # pylint: disable=wrong-import-position

target_metadata = Base.metadata


def _url() -> str:
    return settings.database_url.replace("+asyncpg", "+psycopg")


def run_migrations_offline() -> None:
    """Emit the migration SQL without a database (--sql mode)."""
    context.configure(url=_url(), target_metadata=target_metadata,
                      literal_binds=True)
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    engine = create_engine(_url())
    with engine.connect() as connection:
        context.configure(connection=connection,
                          target_metadata=target_metadata)
        with context.begin_transaction():
            context.run_migrations()
    engine.dispose()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
