"""Chunked bulk writes shared by the SQLite repositories."""

from collections.abc import Mapping, Sequence
from typing import Any

from sqlalchemy import Table
from sqlalchemy.dialects.sqlite import insert
from sqlalchemy.ext.asyncio import AsyncConnection

CHUNK_SIZE = 500


async def upsert_rows(
    conn: AsyncConnection, table: Table, rows: Sequence[Mapping[str, Any]]
) -> int:
    """INSERT ... ON CONFLICT DO UPDATE by primary key, 500 rows per statement."""
    pk = [c.name for c in table.primary_key.columns]
    for i in range(0, len(rows), CHUNK_SIZE):
        stmt = insert(table)
        update = {c.name: stmt.excluded[c.name] for c in table.columns if c.name not in pk}
        await conn.execute(
            stmt.on_conflict_do_update(index_elements=pk, set_=update), rows[i : i + CHUNK_SIZE]
        )
    return len(rows)


async def insert_rows(
    conn: AsyncConnection, table: Table, rows: Sequence[Mapping[str, Any]]
) -> int:
    """Plain INSERT, 500 rows per statement."""
    for i in range(0, len(rows), CHUNK_SIZE):
        await conn.execute(insert(table), rows[i : i + CHUNK_SIZE])
    return len(rows)
