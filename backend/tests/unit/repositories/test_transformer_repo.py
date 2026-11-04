from datetime import UTC, datetime

import pytest
from sqlalchemy.ext.asyncio import AsyncConnection

from app.domain.models import Transformer
from app.portal.fake import FakePortalClient
from app.repositories.sqlite.transformer_repo import SqliteTransformerRepository
from tests.support.portal_emulator import FIXTURES

pytestmark = pytest.mark.anyio
T0 = datetime(2026, 7, 1, tzinfo=UTC)


async def test_fixture_transformers_round_trip(conn: AsyncConnection) -> None:
    portal = FakePortalClient(FIXTURES)
    items: list[Transformer] = []
    page = 1
    while True:
        result = await portal.list_transformers(page)
        if not result.items:
            break
        items.extend(result.items)
        page += 1
    assert items
    repo = SqliteTransformerRepository(conn)
    assert await repo.upsert_many(items, T0) == len(items)
    assert await repo.count() == len(items)
    assert await repo.list_all() == sorted(items, key=lambda t: t.code)
    assert await repo.get(items[0].code) == items[0]


async def test_missing_none_and_empty(conn: AsyncConnection) -> None:
    repo = SqliteTransformerRepository(conn)
    assert await repo.get("x") is None
    assert await repo.upsert_many([], T0) == 0
    assert await repo.count() == 0


async def test_upsert_idempotent_and_updates(conn: AsyncConnection) -> None:
    repo = SqliteTransformerRepository(conn)
    await repo.upsert_many([Transformer("A", "a", None, 10)], T0)
    await repo.upsert_many([Transformer("A", "a", None, 10)], T0)
    assert await repo.count() == 1
    await repo.upsert_many([Transformer("A", "renamed", "F1", 25)], T0)
    assert await repo.get("A") == Transformer("A", "renamed", "F1", 25)


async def test_chunking(conn: AsyncConnection) -> None:
    many = [Transformer(f"T{i:05d}", f"n{i}", None, i) for i in range(1100)]
    repo = SqliteTransformerRepository(conn)
    assert await repo.upsert_many(many, T0) == 1100
    assert await repo.count() == 1100
