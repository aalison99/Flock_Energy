from datetime import UTC, date, datetime, timedelta, timezone

import pytest

from app.domain.exceptions import NotFoundError, ValidationError
from app.domain.models import Reading
from app.portal.fake import FakePortalClient
from app.services.reading_service import ReadingService
from app.services.readings.buckets import Resolution
from tests.support.fake_clock import FakeClock
from tests.support.fakes import FakeFreshness
from tests.support.portal_emulator import FIXTURES

IST = timezone(timedelta(hours=5, minutes=30))
NOW = datetime(2026, 11, 4, 12, tzinfo=UTC)
D = date(2026, 6, 29)


@pytest.fixture
def portal() -> FakePortalClient:
    return FakePortalClient(FIXTURES)


@pytest.fixture
def freshness() -> FakeFreshness:
    return FakeFreshness()


@pytest.fixture
def service(portal: FakePortalClient, freshness: FakeFreshness) -> ReadingService:
    return ReadingService(portal, freshness, FakeClock(NOW))


@pytest.mark.anyio
async def test_start_after_end_raises_before_any_portal_call(
    service: ReadingService, portal: FakePortalClient
) -> None:
    with pytest.raises(ValidationError) as exc:
        await service.get_readings("J100000", date(2026, 6, 30), D, Resolution.RAW)
    assert exc.value.details == {"start": "2026-06-30", "end": "2026-06-29"}
    assert portal.calls == []


@pytest.mark.anyio
async def test_passes_range_through_exactly_once(
    service: ReadingService, portal: FakePortalClient
) -> None:
    await service.get_readings("J100000", D, date(2026, 6, 30), Resolution.RAW)
    assert portal.calls == [("get_readings", ("J100000", D, date(2026, 6, 30)))]


@pytest.mark.anyio
async def test_not_found_propagates(service: ReadingService) -> None:
    with pytest.raises(NotFoundError):
        await service.get_readings("J999999", None, None, Resolution.RAW)


@pytest.mark.anyio
async def test_finer_than_interval_is_validation_error(service: ReadingService) -> None:
    with pytest.raises(ValidationError) as exc:
        await service.get_readings("J100402", None, None, Resolution.HOURLY)
    assert (
        exc.value.message == "resolution 'hourly' is finer than this meter's 1440-minute interval"
    )
    assert exc.value.details == {"resolution": "hourly", "interval_minutes": 1440}


@pytest.mark.anyio
async def test_raw_always_allowed_and_daily_ok_on_daily_meter(service: ReadingService) -> None:
    raw = await service.get_readings("J100402", None, None, Resolution.RAW)
    assert raw.points is not None and raw.buckets is None and len(raw.points) == 8
    daily = await service.get_readings("J100402", None, None, Resolution.DAILY)
    assert daily.buckets is not None and daily.points is None and len(daily.buckets) == 7
    assert daily.interval_kind == "daily"


@pytest.mark.anyio
async def test_meta_from_freshness(service: ReadingService, freshness: FakeFreshness) -> None:
    at = datetime(2026, 11, 4, 9, tzinfo=UTC)
    freshness.set("get_readings", "J100000", D, D, fetched_at=at, expires_at=NOW, stale=True)
    result = await service.get_readings("J100000", D, D, Resolution.RAW)
    assert (result.meta.fetched_at, result.meta.stale) == (at, True)


@pytest.mark.anyio
async def test_meta_fallback_is_now_not_stale(service: ReadingService) -> None:
    result = await service.get_readings("J100000", D, D, Resolution.RAW)
    assert (result.meta.source, result.meta.fetched_at, result.meta.stale) == ("portal", NOW, False)


@pytest.mark.anyio
async def test_summary_totals(service: ReadingService) -> None:
    result = await service.get_readings("J100402", None, None, Resolution.RAW)
    s = result.summary
    assert s.readings == 8 and s.gaps == 0 and s.resets == 0
    assert s.total_kwh == 149.24  # 25842.60 - 25693.36
    assert s.total_kvah == 161.17  # 27910.00 - 27748.83
    assert s.avg_voltage == 227.4  # (229+229+221+221+230+234+233+222)/8 = 227.375
    assert s.first_at is not None and s.first_at.isoformat() == "2026-06-23T00:00:00+05:30"
    assert s.last_at is not None and s.last_at.isoformat() == "2026-06-30T00:00:00+05:30"


@pytest.mark.anyio
async def test_empty_range(service: ReadingService) -> None:
    result = await service.get_readings(
        "J100000", date(2030, 1, 1), date(2030, 1, 2), Resolution.HOURLY
    )
    assert result.buckets == [] and result.points is None
    assert result.interval_minutes is None and result.interval_kind == "unknown"
    s = result.summary
    assert (s.total_kwh, s.total_kvah, s.avg_voltage, s.readings, s.gaps, s.resets) == (
        0.0, 0.0, None, 0, 0, 0,
    )  # fmt: skip
    assert s.first_at is None and s.last_at is None


@pytest.mark.anyio
async def test_empty_raw_has_empty_points(service: ReadingService) -> None:
    result = await service.get_readings("J100000", date(2030, 1, 1), None, Resolution.RAW)
    assert result.points == [] and result.buckets is None


class _Scripted(FakePortalClient):
    def __init__(self, readings: list[Reading]) -> None:
        super().__init__(FIXTURES)
        self._readings = readings

    async def get_readings(
        self, meter_id: str, start: date | None = None, end: date | None = None
    ) -> list[Reading]:
        return self._readings


@pytest.mark.anyio
async def test_gaps_resets_and_totals_in_summary() -> None:
    def r(m: int, kwh: float, kvah: float, v: float | None = 230.0) -> Reading:
        return Reading(datetime(2026, 6, 24, tzinfo=IST) + timedelta(minutes=m), kwh, kvah, v)

    readings = [
        r(0, 10.0, 12.0),
        r(30, 11.0, 13.0),
        r(60, 12.0, 14.0),
        r(180, 15.0, 17.0),  # 2h span on a 30 min cadence -> 3 missing
        r(210, 1.0, 18.0),  # kWh reset
    ]
    service = ReadingService(_Scripted(readings), FakeFreshness(), FakeClock(NOW))
    result = await service.get_readings("J100000", None, None, Resolution.RAW)
    assert result.interval_minutes == 30
    s = result.summary
    assert (s.gaps, s.resets, s.readings) == (3, 1, 5)
    assert s.total_kwh == 5.0  # 1 + 1 + 3, the reset interval is excluded
    assert s.total_kvah == 5.0  # 1 + 1 + 3


@pytest.mark.anyio
async def test_single_reading() -> None:
    one = [Reading(datetime(2026, 6, 24, tzinfo=IST), 10.0, 12.0, 230.0)]
    service = ReadingService(_Scripted(one), FakeFreshness(), FakeClock(NOW))
    result = await service.get_readings("J100000", None, None, Resolution.RAW)
    assert result.interval_minutes is None and result.interval_kind == "unknown"
    assert result.points is not None and len(result.points) == 1
    s = result.summary
    assert (s.readings, s.total_kwh, s.total_kvah, s.gaps, s.resets) == (1, 0.0, 0.0, 0, 0)
    assert s.first_at == s.last_at is not None
    hourly = await service.get_readings("J100000", None, None, Resolution.HOURLY)
    assert hourly.buckets == []


@pytest.mark.anyio
async def test_summary_avg_voltage_one_decimal() -> None:
    base = datetime(2026, 6, 24, tzinfo=IST)
    rows = [
        Reading(base + timedelta(minutes=30 * i), float(i), float(i), v)
        for i, v in enumerate([229.0, 230.0, 230.5])
    ]
    service = ReadingService(_Scripted(rows), FakeFreshness(), FakeClock(NOW))
    result = await service.get_readings("J100000", None, None, Resolution.RAW)
    assert result.summary.avg_voltage == 229.8  # 689.5 / 3 = 229.833
