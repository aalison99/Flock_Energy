import sqlite3
from pathlib import Path

import pytest
from alembic.autogenerate import compare_metadata
from alembic.migration import MigrationContext
from sqlalchemy import create_engine

from app.db.engine import downgrade_migrations, run_migrations
from app.db.tables import metadata

EXPECTED_INDEXES = {
    "ix_meters_install_status",
    "ix_meters_make",
    "ix_meters_phase_type",
    "ix_meters_dt_code",
    "ix_meters_feeder_code",
    "ix_meters_substation_code",
    "ix_meters_lat_lng",
    "ux_sync_runs_one_running",
}


def _names(path: Path, kind: str) -> set[str]:
    with sqlite3.connect(path) as db:
        rows = db.execute("SELECT name FROM sqlite_master WHERE type=?", (kind,)).fetchall()
    return {r[0] for r in rows}


def test_upgrade_creates_tables_and_indexes(tmp_path: Path) -> None:
    path = tmp_path / "m.db"
    run_migrations(f"sqlite:///{path}")
    assert {"meters", "transformers", "readings", "sync_runs"} <= _names(path, "table")
    assert _names(path, "index") >= EXPECTED_INDEXES


def test_partial_unique_index_is_partial(tmp_path: Path) -> None:
    path = tmp_path / "m.db"
    run_migrations(f"sqlite:///{path}")
    with sqlite3.connect(path) as db:
        (sql,) = db.execute(
            "SELECT sql FROM sqlite_master WHERE name='ux_sync_runs_one_running'"
        ).fetchone()
    assert "UNIQUE" in sql.upper()
    assert "WHERE" in sql.upper()
    assert "'running'" in sql


def test_upgrade_downgrade_upgrade_round_trip(tmp_path: Path) -> None:
    url = f"sqlite:///{tmp_path / 'm.db'}"
    run_migrations(url)
    downgrade_migrations(url)
    assert _names(tmp_path / "m.db", "table") <= {"alembic_version", "sqlite_sequence"}
    run_migrations(url)
    assert "meters" in _names(tmp_path / "m.db", "table")


def test_run_migrations_is_idempotent(tmp_path: Path) -> None:
    url = f"sqlite:///{tmp_path / 'm.db'}"
    run_migrations(url)
    run_migrations(url)


def test_schema_matches_tables(tmp_path: Path) -> None:
    url = f"sqlite:///{tmp_path / 'm.db'}"
    run_migrations(url)
    engine = create_engine(url)
    with engine.connect() as connection:
        ctx = MigrationContext.configure(connection, opts={"compare_type": True})
        assert compare_metadata(ctx, metadata) == []
    engine.dispose()


def test_partial_index_where_clause_exact_and_behaviour(tmp_path: Path) -> None:
    path = tmp_path / "m.db"
    run_migrations(f"sqlite:///{path}")
    with sqlite3.connect(path) as db:
        (sql,) = db.execute(
            "SELECT sql FROM sqlite_master WHERE name='ux_sync_runs_one_running'"
        ).fetchone()
        assert sql.endswith("WHERE status = 'running'")
        ins = "INSERT INTO sync_runs (status, started_at) VALUES (?, 'x')"
        db.execute(ins, ("running",))
        db.execute(ins, ("failed",))
        db.execute(ins, ("failed",))
        with pytest.raises(sqlite3.IntegrityError):
            db.execute(ins, ("running",))
