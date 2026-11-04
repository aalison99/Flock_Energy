"""Fixtures for database tests: a migrated temp SQLite file and a transactional connection."""

from collections.abc import AsyncIterator
from pathlib import Path

import pytest
from sqlalchemy.ext.asyncio import AsyncConnection, AsyncEngine

from app.db.engine import make_async_engine, run_migrations


@pytest.fixture
def db_url(tmp_path: Path) -> str:
    url = f"sqlite:///{tmp_path / 't.db'}"
    run_migrations(url)
    return url


@pytest.fixture
async def engine(db_url: str) -> AsyncIterator[AsyncEngine]:
    eng = make_async_engine(db_url)
    try:
        yield eng
    finally:
        await eng.dispose()


@pytest.fixture
async def conn(engine: AsyncEngine) -> AsyncIterator[AsyncConnection]:
    """A connection inside a transaction that is rolled back at the end."""
    async with engine.connect() as connection:
        trans = await connection.begin()
        try:
            yield connection
        finally:
            await trans.rollback()
