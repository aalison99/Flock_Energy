"""SQLAlchemy Core table definitions: the single source of truth for schema v1."""

from sqlalchemy import (
    REAL,
    Boolean,
    Column,
    ForeignKey,
    Index,
    Integer,
    MetaData,
    Table,
    Text,
    text,
)

from app.domain.models import HIERARCHY_LEVELS

metadata = MetaData()

# The dt level's code is stored as `dt_node_code`; `dt_code` is the meter's own DT field.
_hierarchy_columns = [
    Column(
        "dt_node_code" if (level.value, part) == ("dt", "code") else f"{level.value}_{part}",
        Text,
        nullable=True,
    )
    for level in HIERARCHY_LEVELS
    for part in ("code", "name")
]

meters = Table(
    "meters",
    metadata,
    Column("meter_id", Text, primary_key=True),
    Column("serial_no", Text, nullable=False),
    Column("make", Text, nullable=False),
    Column("phase_type", Text, nullable=False),
    Column("install_status", Text, nullable=False),
    Column("install_type", Text, nullable=True),
    Column("build", Text, nullable=True),
    Column("dt_code", Text, nullable=True),
    *_hierarchy_columns,
    Column("has_hierarchy", Boolean, nullable=False),
    Column("lat", REAL, nullable=True),
    Column("lng", REAL, nullable=True),
    Column("synced_at", Text, nullable=False),
    Index("ix_meters_install_status", "install_status"),
    Index("ix_meters_make", "make"),
    Index("ix_meters_phase_type", "phase_type"),
    Index("ix_meters_dt_code", "dt_code"),
    Index("ix_meters_feeder_code", "feeder_code"),
    Index("ix_meters_substation_code", "substation_code"),
    Index("ix_meters_lat_lng", "lat", "lng"),
)

transformers = Table(
    "transformers",
    metadata,
    Column("code", Text, primary_key=True),
    Column("name", Text, nullable=False),
    Column("feeder_code", Text, nullable=True),
    Column("capacity_kva", Integer, nullable=False),
    Column("synced_at", Text, nullable=False),
)

readings = Table(
    "readings",
    metadata,
    Column(
        "meter_id",
        Text,
        ForeignKey("meters.meter_id", ondelete="CASCADE"),
        primary_key=True,
        nullable=False,
    ),
    Column("at", Text, primary_key=True, nullable=False),
    Column("kwh_register", REAL, nullable=False),
    Column("kvah_register", REAL, nullable=False),
    Column("voltage_r", REAL, nullable=True),
)

sync_runs = Table(
    "sync_runs",
    metadata,
    Column("id", Integer, primary_key=True, autoincrement=True),
    Column("status", Text, nullable=False),
    Column("strategy", Text, nullable=True),
    Column("started_at", Text, nullable=False),
    Column("finished_at", Text, nullable=True),
    Column("counts", Text, nullable=False, server_default=text("'{}'")),
    Column("error", Text, nullable=True),
    Index(
        "ux_sync_runs_one_running",
        "status",
        unique=True,
        sqlite_where=text("status = 'running'"),
    ),
)
