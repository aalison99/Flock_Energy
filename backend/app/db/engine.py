"""Async SQLite engine factory and programmatic Alembic migrations."""

from pathlib import Path
from typing import Any

from alembic import command
from alembic.config import Config
from sqlalchemy import event, make_url
from sqlalchemy.ext.asyncio import AsyncEngine, create_async_engine

MIGRATIONS_DIR = Path(__file__).parent / "migrations"


def _sync_url(db_url: str) -> str:
    """Normalise to the plain `sqlite:///` form (drops any async driver suffix)."""
    return db_url.replace("sqlite+aiosqlite:", "sqlite:", 1)


def make_async_engine(db_url: str, busy_timeout_ms: int = 5000) -> AsyncEngine:
    """Create the async engine; every connection gets FK enforcement, WAL and a busy timeout."""
    url = make_url(_sync_url(db_url)).set(drivername="sqlite+aiosqlite")
    if url.database and url.database != ":memory:":
        Path(url.database).parent.mkdir(parents=True, exist_ok=True)
    engine = create_async_engine(url)

    @event.listens_for(engine.sync_engine, "connect")
    def _set_pragmas(dbapi_connection: Any, _record: Any) -> None:
        # Take over transaction control from pysqlite (see _begin), so SAVEPOINT as the first
        # statement cannot commit the caller's transaction.
        dbapi_connection.isolation_level = None
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.execute("PRAGMA journal_mode=WAL")
        cursor.execute(f"PRAGMA busy_timeout={int(busy_timeout_ms)}")
        cursor.close()

    @event.listens_for(engine.sync_engine, "begin")
    def _begin(conn: Any) -> None:
        conn.exec_driver_sql("BEGIN")

    return engine


def _alembic_config(db_url: str) -> Config:
    url = _sync_url(db_url)
    database = make_url(url).database
    if database and database != ":memory:":
        Path(database).parent.mkdir(parents=True, exist_ok=True)
    config = Config()
    config.set_main_option("script_location", str(MIGRATIONS_DIR))
    config.set_main_option("sqlalchemy.url", url.replace("%", "%%"))
    return config


def run_migrations(db_url: str) -> None:
    """Run `alembic upgrade head` against a (sync) SQLite URL."""
    command.upgrade(_alembic_config(db_url), "head")


def downgrade_migrations(db_url: str, revision: str = "base") -> None:
    """Run `alembic downgrade <revision>` (tests and manual recovery)."""
    command.downgrade(_alembic_config(db_url), revision)
