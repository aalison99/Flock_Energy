"""Alembic environment: sync SQLite engine from the configured URL, tables.metadata as target."""

from alembic import context
from sqlalchemy import create_engine

from app.db.tables import metadata

config = context.config


def run_migrations_online() -> None:
    engine = create_engine(config.get_main_option("sqlalchemy.url") or "")
    with engine.connect() as connection:
        context.configure(connection=connection, target_metadata=metadata, render_as_batch=True)
        with context.begin_transaction():
            context.run_migrations()
    engine.dispose()


run_migrations_online()
