"""SQLite implementation of MeterRepository."""

from collections.abc import Collection, Sequence
from datetime import datetime

from sqlalchemy import ColumnElement, desc, func, or_, select
from sqlalchemy.ext.asyncio import AsyncConnection

from app.db.tables import meters
from app.domain.models import Meter, PageResult
from app.repositories.interfaces import MeterQuery
from app.repositories.sqlite import mapping
from app.repositories.sqlite._bulk import delete_missing, upsert_rows

_c = meters.c
# Registries: query field -> column. Adding a filter or sort key is a new row, not a new branch.
_EQUALS = {
    "phase": _c.phase_type,
    "install_type": _c.install_type,
    "dt": _c.dt_code,
    "feeder": _c.feeder_code,
    "substation": _c.substation_code,
    "subdivision": _c.subdivision_code,
    "division": _c.division_code,
    "circle": _c.circle_code,
    "zone": _c.zone_code,
}
_ANY_OF = {"status": _c.install_status, "make": _c.make}
_FACET_COLUMNS = {
    "status": _c.install_status,
    "make": _c.make,
    "phase": _c.phase_type,
    "install_type": _c.install_type,
    "dt": _c.dt_code,
}
_SORTS = {
    "meter_id": (_c.meter_id,),
    "-meter_id": (desc(_c.meter_id),),
    "make": (_c.make, _c.meter_id),
    "status": (_c.install_status, _c.meter_id),
}


def _escape_like(text: str) -> str:
    return text.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")


def _conditions(f: MeterQuery) -> list[ColumnElement[bool]]:
    found: list[ColumnElement[bool]] = []
    if f.q is not None:
        pattern = f"%{_escape_like(f.q.lower())}%"
        found.append(
            or_(
                func.lower(_c.meter_id).like(pattern, escape="\\"),
                func.lower(_c.serial_no).like(pattern, escape="\\"),
            )
        )
    for name, column in _ANY_OF.items():
        values = getattr(f, name)
        if values:
            found.append(column.in_(values))
    for name, column in _EQUALS.items():
        value = getattr(f, name)
        if value is not None:
            found.append(column == value)
    if f.has_geo is not None:
        found.append(_c.lat.is_not(None) if f.has_geo else _c.lat.is_(None))
    return found


class SqliteMeterRepository:
    def __init__(self, conn: AsyncConnection) -> None:
        self._conn = conn

    async def upsert_many(self, meters_: Sequence[Meter], synced_at: datetime) -> int:
        rows = [mapping.meter_to_row(m, synced_at) for m in meters_]
        return await upsert_rows(self._conn, meters, rows)

    async def get(self, meter_id: str) -> Meter | None:
        result = await self._conn.execute(select(meters).where(meters.c.meter_id == meter_id))
        row = result.mappings().first()
        return mapping.row_to_meter(row) if row else None

    async def count(self) -> int:
        return (await self._conn.execute(select(func.count()).select_from(meters))).scalar_one()

    async def list_all(self) -> list[Meter]:
        result = await self._conn.execute(select(meters).order_by(meters.c.meter_id))
        return [mapping.row_to_meter(r) for r in result.mappings()]

    async def delete_missing(self, keep_ids: Collection[str]) -> int:
        return await delete_missing(self._conn, meters, meters.c.meter_id, keep_ids)

    async def search(self, filters: MeterQuery, page: int, page_size: int) -> PageResult[Meter]:
        where = _conditions(filters)
        total = (
            await self._conn.execute(select(func.count()).select_from(meters).where(*where))
        ).scalar_one()
        stmt = (
            select(meters)
            .where(*where)
            .order_by(*_SORTS[filters.sort])
            .limit(page_size)
            .offset((page - 1) * page_size)
        )
        rows = (await self._conn.execute(stmt)).mappings()
        return PageResult(items=[mapping.row_to_meter(r) for r in rows], total=total)

    async def facet_counts(self, filters: MeterQuery, field: str) -> dict[str, int]:
        column = _FACET_COLUMNS[field]
        stmt = (
            select(column, func.count())
            .where(*_conditions(filters), column.is_not(None))
            .group_by(column)
        )
        return {value: count for value, count in (await self._conn.execute(stmt)).all()}

    async def get_synced_at(self, meter_id: str) -> datetime | None:
        stmt = select(_c.synced_at).where(_c.meter_id == meter_id)
        text = (await self._conn.execute(stmt)).scalar_one_or_none()
        return mapping.parse_time(text) if text is not None else None

    async def within_box(
        self,
        min_lat: float,
        min_lng: float,
        max_lat: float,
        max_lng: float,
        filters: MeterQuery,
        limit: int,
    ) -> list[Meter]:
        stmt = (
            select(meters)
            .where(
                *_conditions(filters),
                _c.lat.between(min_lat, max_lat),
                _c.lng.between(min_lng, max_lng),
            )
            .order_by(_c.meter_id)
            .limit(limit)
        )
        return [mapping.row_to_meter(r) for r in (await self._conn.execute(stmt)).mappings()]
