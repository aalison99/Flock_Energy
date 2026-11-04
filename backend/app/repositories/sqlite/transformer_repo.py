"""SQLite implementation of TransformerRepository."""

from collections.abc import Collection, Sequence
from datetime import datetime

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncConnection

from app.db.tables import transformers
from app.domain.models import Transformer
from app.repositories.sqlite import mapping
from app.repositories.sqlite._bulk import delete_missing, upsert_rows


class SqliteTransformerRepository:
    def __init__(self, conn: AsyncConnection) -> None:
        self._conn = conn

    async def upsert_many(self, items: Sequence[Transformer], synced_at: datetime) -> int:
        rows = [mapping.transformer_to_row(t, synced_at) for t in items]
        return await upsert_rows(self._conn, transformers, rows)

    async def get(self, code: str) -> Transformer | None:
        result = await self._conn.execute(select(transformers).where(transformers.c.code == code))
        row = result.mappings().first()
        return mapping.row_to_transformer(row) if row else None

    async def list_all(self) -> list[Transformer]:
        result = await self._conn.execute(select(transformers).order_by(transformers.c.code))
        return [mapping.row_to_transformer(r) for r in result.mappings()]

    async def count(self) -> int:
        stmt = select(func.count()).select_from(transformers)
        return (await self._conn.execute(stmt)).scalar_one()

    async def delete_missing(self, keep_codes: Collection[str]) -> int:
        return await delete_missing(self._conn, transformers, transformers.c.code, keep_codes)
