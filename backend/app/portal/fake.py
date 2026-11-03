"""Fixture-backed PortalClient that runs the real parsers on saved payloads; injects failures."""

from dataclasses import dataclass, replace
from datetime import date
from pathlib import Path
from typing import cast

from app.domain.exceptions import NotFoundError
from app.domain.models import GeoPoint, Meter, Reading, Transformer
from app.portal.interfaces import PortalPage
from app.portal.parsers.registry import PayloadKind, default_registry

PAGE_SIZE = 20
_DT_TOTAL = 40


@dataclass
class _Failure:
    error: Exception
    start: int | None
    remaining: int


class FakePortalClient:
    """In-memory portal built from the sanitised fixtures; implements PortalClient."""

    def __init__(self, fixtures_dir: Path) -> None:
        self._dir = fixtures_dir
        self._parsers = default_registry()
        raw = (fixtures_dir / "export" / "export_page1.json").read_bytes()
        self._meters = cast(list[Meter], self._parsers.parse(PayloadKind.EXPORT, raw))
        self._by_id = {m.meter_id: m for m in self._meters}
        self.calls: list[tuple[str, tuple[object, ...]]] = []
        self.closed = False
        self._counts: dict[str, int] = {}
        self._failures: dict[str, list[_Failure]] = {}

    def fail(
        self, method: str, error: Exception, *, on_call: int | None = None, times: int = 1
    ) -> None:
        """Make `method` raise `error` `times` times, from its `on_call`-th call (default next)."""
        self._failures.setdefault(method, []).append(_Failure(error, on_call, times))

    def _enter(self, method: str, *args: object) -> None:
        self.calls.append((method, args))
        count = self._counts.get(method, 0) + 1
        self._counts[method] = count
        for failure in self._failures.get(method, []):
            if failure.remaining > 0 and (failure.start is None or count >= failure.start):
                failure.remaining -= 1
                raise failure.error

    def _known(self, meter_id: str) -> Meter:
        try:
            return self._by_id[meter_id]
        except KeyError:
            raise NotFoundError("Meter not found") from None

    async def list_meters(self, page: int, query: str | None = None) -> PortalPage[Meter]:
        self._enter("list_meters", page, query)
        page = max(page, 1)
        needle = (query or "").lower()
        matches = [
            m for m in self._meters if needle in m.meter_id.lower() or needle in m.serial_no.lower()
        ]
        window = matches[(page - 1) * PAGE_SIZE : page * PAGE_SIZE]
        items = tuple(
            replace(m, install_type=None, build=None, hierarchy=None, geo=None) for m in window
        )
        return PortalPage(items=items, total=len(matches), page=page, page_size=PAGE_SIZE)

    async def get_meter(self, meter_id: str) -> Meter:
        self._enter("get_meter", meter_id)
        return replace(self._known(meter_id), geo=None)

    async def get_geo(self, meter_id: str) -> GeoPoint | None:
        self._enter("get_geo", meter_id)
        return self._known(meter_id).geo

    async def get_readings(
        self, meter_id: str, start: date | None = None, end: date | None = None
    ) -> list[Reading]:
        self._enter("get_readings", meter_id, start, end)
        self._known(meter_id)
        files = sorted((self._dir / "energy").glob(f"*_{meter_id}.json"))
        if not files:
            return []
        readings = cast(
            list[Reading], self._parsers.parse(PayloadKind.ENERGY, files[0].read_bytes())
        )
        return [
            r
            for r in readings
            if (start is None or r.at.date() >= start) and (end is None or r.at.date() <= end)
        ]

    async def list_transformers(self, page: int) -> PortalPage[Transformer]:
        self._enter("list_transformers", page)
        page = max(page, 1)
        path = self._dir / "dts" / f"page{page}.json"
        if page > 2 or not path.exists():
            return PortalPage(items=(), total=_DT_TOTAL, page=page, page_size=PAGE_SIZE)
        return cast(
            PortalPage[Transformer], self._parsers.parse(PayloadKind.DT_PAGE, path.read_bytes())
        )

    async def bulk_export(self) -> list[Meter]:
        self._enter("bulk_export")
        return list(self._meters)

    async def aclose(self) -> None:
        self._enter("aclose")
        self.closed = True
