"""SQLite implementation of IndexStore: one engine transaction per `transaction()` block."""

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from sqlalchemy.ext.asyncio import AsyncEngine

from app.repositories.interfaces import IndexRepos
from app.repositories.sqlite.meter_repo import SqliteMeterRepository
from app.repositories.sqlite.reading_repo import SqliteReadingRepository
from app.repositories.sqlite.sync_repo import SqliteSyncRepository
from app.repositories.sqlite.transformer_repo import SqliteTransformerRepository


class SqliteIndexStore:
    def __init__(self, engine: AsyncEngine) -> None:
        self._engine = engine

    @asynccontextmanager
    async def transaction(self) -> AsyncIterator[IndexRepos]:
        async with self._engine.begin() as conn:
            yield IndexRepos(
                meters=SqliteMeterRepository(conn),
                transformers=SqliteTransformerRepository(conn),
                readings=SqliteReadingRepository(conn),
                runs=SqliteSyncRepository(conn),
            )
