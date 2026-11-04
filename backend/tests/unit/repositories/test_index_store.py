from datetime import UTC, datetime

import pytest
from sqlalchemy.ext.asyncio import AsyncEngine

from app.portal.fake import FakePortalClient
from app.repositories.sqlite.store import SqliteIndexStore
from tests.support.portal_emulator import FIXTURES

pytestmark = pytest.mark.anyio
T0 = datetime(2026, 7, 1, tzinfo=UTC)


async def test_transaction_commits_on_exit(engine: AsyncEngine) -> None:
    meters = (await FakePortalClient(FIXTURES).bulk_export())[:3]
    store = SqliteIndexStore(engine)
    async with store.transaction() as repos:
        await repos.meters.upsert_many(meters, T0)
        await repos.runs.start_run(T0)
    async with store.transaction() as repos:
        assert await repos.meters.count() == 3
        assert await repos.runs.current() is not None
        assert await repos.readings.count() == 0
        assert await repos.transformers.count() == 0


async def test_transaction_rolls_back_on_error(engine: AsyncEngine) -> None:
    meters = (await FakePortalClient(FIXTURES).bulk_export())[:3]
    store = SqliteIndexStore(engine)
    with pytest.raises(RuntimeError):
        async with store.transaction() as repos:
            await repos.meters.upsert_many(meters, T0)
            raise RuntimeError("boom")
    async with store.transaction() as repos:
        assert await repos.meters.count() == 0
