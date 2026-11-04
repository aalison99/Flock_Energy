from pathlib import Path

import pytest
from sqlalchemy import text

from app.db.engine import make_async_engine

pytestmark = pytest.mark.anyio


def test_url_is_converted_to_aiosqlite(tmp_path: Path) -> None:
    engine = make_async_engine(f"sqlite:///{tmp_path / 'a.db'}")
    assert engine.url.drivername == "sqlite+aiosqlite"


def test_parent_directory_is_created(tmp_path: Path) -> None:
    target = tmp_path / "nested" / "dir" / "a.db"
    make_async_engine(f"sqlite:///{target}")
    assert target.parent.is_dir()


async def test_pragmas_are_on_for_every_connection(tmp_path: Path) -> None:
    engine = make_async_engine(f"sqlite:///{tmp_path / 'a.db'}")
    try:
        for _ in range(2):
            async with engine.connect() as conn:
                fk = (await conn.execute(text("PRAGMA foreign_keys"))).scalar_one()
                mode = (await conn.execute(text("PRAGMA journal_mode"))).scalar_one()
                busy = (await conn.execute(text("PRAGMA busy_timeout"))).scalar_one()
                assert (fk, mode, busy) == (1, "wal", 5000)
    finally:
        await engine.dispose()
