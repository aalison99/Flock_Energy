"""Initial schema: meters, transformers, readings, sync_runs.

Revision ID: 0001
Revises:
"""

import sqlalchemy as sa
from alembic import op

revision = "0001"
down_revision = None
branch_labels = None
depends_on = None

_LEVELS = ("zone", "circle", "division", "subdivision", "substation", "feeder", "dt")


def upgrade() -> None:
    hierarchy = [
        sa.Column(
            "dt_node_code" if (level, part) == ("dt", "code") else f"{level}_{part}",
            sa.Text(),
            nullable=True,
        )
        for level in _LEVELS
        for part in ("code", "name")
    ]
    op.create_table(
        "meters",
        sa.Column("meter_id", sa.Text(), nullable=False),
        sa.Column("serial_no", sa.Text(), nullable=False),
        sa.Column("make", sa.Text(), nullable=False),
        sa.Column("phase_type", sa.Text(), nullable=False),
        sa.Column("install_status", sa.Text(), nullable=False),
        sa.Column("install_type", sa.Text(), nullable=True),
        sa.Column("build", sa.Text(), nullable=True),
        sa.Column("dt_code", sa.Text(), nullable=True),
        *hierarchy,
        sa.Column("has_hierarchy", sa.Boolean(), nullable=False),
        sa.Column("lat", sa.REAL(), nullable=True),
        sa.Column("lng", sa.REAL(), nullable=True),
        sa.Column("synced_at", sa.Text(), nullable=False),
        sa.PrimaryKeyConstraint("meter_id"),
    )
    op.create_index("ix_meters_install_status", "meters", ["install_status"])
    op.create_index("ix_meters_make", "meters", ["make"])
    op.create_index("ix_meters_phase_type", "meters", ["phase_type"])
    op.create_index("ix_meters_dt_code", "meters", ["dt_code"])
    op.create_index("ix_meters_feeder_code", "meters", ["feeder_code"])
    op.create_index("ix_meters_substation_code", "meters", ["substation_code"])
    op.create_index("ix_meters_lat_lng", "meters", ["lat", "lng"])

    op.create_table(
        "transformers",
        sa.Column("code", sa.Text(), nullable=False),
        sa.Column("name", sa.Text(), nullable=False),
        sa.Column("feeder_code", sa.Text(), nullable=True),
        sa.Column("capacity_kva", sa.Integer(), nullable=False),
        sa.Column("synced_at", sa.Text(), nullable=False),
        sa.PrimaryKeyConstraint("code"),
    )

    op.create_table(
        "readings",
        sa.Column("meter_id", sa.Text(), nullable=False),
        sa.Column("at", sa.Text(), nullable=False),
        sa.Column("kwh_register", sa.REAL(), nullable=False),
        sa.Column("kvah_register", sa.REAL(), nullable=False),
        sa.Column("voltage_r", sa.REAL(), nullable=True),
        sa.ForeignKeyConstraint(["meter_id"], ["meters.meter_id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("meter_id", "at"),
    )

    op.create_table(
        "sync_runs",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("status", sa.Text(), nullable=False),
        sa.Column("strategy", sa.Text(), nullable=True),
        sa.Column("started_at", sa.Text(), nullable=False),
        sa.Column("finished_at", sa.Text(), nullable=True),
        sa.Column("counts", sa.Text(), server_default=sa.text("'{}'"), nullable=False),
        sa.Column("error", sa.Text(), nullable=True),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ux_sync_runs_one_running",
        "sync_runs",
        ["status"],
        unique=True,
        sqlite_where=sa.text("status = 'running'"),
    )


def downgrade() -> None:
    op.drop_index("ux_sync_runs_one_running", table_name="sync_runs")
    op.drop_table("sync_runs")
    op.drop_table("readings")
    op.drop_table("transformers")
    for name in (
        "ix_meters_lat_lng",
        "ix_meters_substation_code",
        "ix_meters_feeder_code",
        "ix_meters_dt_code",
        "ix_meters_phase_type",
        "ix_meters_make",
        "ix_meters_install_status",
    ):
        op.drop_index(name, table_name="meters")
    op.drop_table("meters")
