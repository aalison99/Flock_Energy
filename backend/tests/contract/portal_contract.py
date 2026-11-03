"""Reusable PortalClient contract: subclass and provide a `portal` fixture (fake now, HTTP in M2b).

Only behaviour documented in PROTOCOL.md is asserted here.
"""

from datetime import date, datetime, timedelta, timezone

import pytest

from app.domain.exceptions import NotFoundError
from app.domain.models import InstallStatus, InstallType, NodeRef
from app.portal.interfaces import PortalClient

IST = timezone(timedelta(hours=5, minutes=30))


@pytest.mark.anyio
class PortalClientContract:
    """Subclasses define `portal() -> PortalClient`."""

    async def test_list_page_1(self, portal: PortalClient) -> None:
        page = await portal.list_meters(1)
        assert (len(page.items), page.total, page.page_size, page.page) == (20, 403, 20, 1)

    async def test_list_last_and_past_end(self, portal: PortalClient) -> None:
        assert len((await portal.list_meters(21)).items) == 3
        past = await portal.list_meters(22)
        assert past.items == () and past.total == 403

    async def test_list_page_below_one_is_page_one(self, portal: PortalClient) -> None:
        first = await portal.list_meters(1)
        assert (await portal.list_meters(0)).items == first.items

    async def test_query_substring(self, portal: PortalClient) -> None:
        page = await portal.list_meters(1, "0001")
        ids = {m.meter_id for m in page.items}
        assert len(ids) == 11 and page.total == 11
        assert {"J100001", *(f"J1000{n}" for n in range(10, 20))} == ids

    async def test_query_serial_case_insensitive(self, portal: PortalClient) -> None:
        page = await portal.list_meters(1, "se33962")
        assert [m.meter_id for m in page.items] == ["J100000"]

    async def test_query_only_matches_id_and_serial(self, portal: PortalClient) -> None:
        assert (await portal.list_meters(1, "HPL")).items == ()

    async def test_get_meter(self, portal: PortalClient) -> None:
        m = await portal.get_meter("J100000")
        assert (m.serial_no, m.make) == ("SE33962", "HPL")
        assert m.install_status is InstallStatus.DECOMMISSIONED
        assert m.install_type is InstallType.WHOLE_CURRENT
        assert m.hierarchy is not None
        assert m.hierarchy.dt == NodeRef("DT-001", "Malviya Nagar DT 1")
        assert m.geo is None

    async def test_get_meter_unknown(self, portal: PortalClient) -> None:
        with pytest.raises(NotFoundError):
            await portal.get_meter("J999999")

    async def test_get_geo(self, portal: PortalClient) -> None:
        geo = await portal.get_geo("J100000")
        assert geo is not None
        assert geo.lat == pytest.approx(26.938961002479868)
        assert geo.lng == pytest.approx(75.83095696146852)

    async def test_readings_half_hourly(self, portal: PortalClient) -> None:
        readings = await portal.get_readings("J100000")
        assert len(readings) == 337
        assert [r.at for r in readings] == sorted(r.at for r in readings)
        assert readings[0].at == datetime(2026, 6, 23, 23, 30, tzinfo=IST)
        assert readings[0].at.utcoffset() == timedelta(hours=5, minutes=30)
        assert readings[0].kwh_register == 48438.74

    async def test_readings_date_filter(self, portal: PortalClient) -> None:
        day = date(2026, 6, 30)
        readings = await portal.get_readings("J100000", day, day)
        assert readings
        assert {r.at.date() for r in readings} == {day}

    async def test_readings_daily(self, portal: PortalClient) -> None:
        readings = await portal.get_readings("J100402")
        assert len(readings) == 8
        assert all((r.at.hour, r.at.minute) == (0, 0) for r in readings)

    async def test_readings_unknown(self, portal: PortalClient) -> None:
        with pytest.raises(NotFoundError):
            await portal.get_readings("J999999")

    async def test_transformers(self, portal: PortalClient) -> None:
        p1, p2 = await portal.list_transformers(1), await portal.list_transformers(2)
        codes = [t.code for t in (*p1.items, *p2.items)]
        assert len(codes) == len(set(codes)) == 40
        assert next(t for t in p1.items if t.code == "DT-001").capacity_kva == 100

    async def test_bulk_export(self, portal: PortalClient) -> None:
        meters = await portal.bulk_export()
        assert len({m.meter_id for m in meters}) == 403
        assert all(m.hierarchy is not None and m.geo is not None for m in meters)

    async def test_aclose_twice(self, portal: PortalClient) -> None:
        await portal.aclose()
        await portal.aclose()
