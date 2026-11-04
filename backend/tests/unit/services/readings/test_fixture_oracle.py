"""Independent oracle: expected numbers come from the raw JSON via Decimal, not from our code."""

import json
from datetime import UTC, date, datetime
from decimal import Decimal

import pytest

from app.portal.fake import FakePortalClient
from app.services.reading_service import ReadingService
from app.services.readings.buckets import Resolution
from tests.support.fake_clock import FakeClock
from tests.support.fakes import FakeFreshness
from tests.support.portal_emulator import FIXTURES

RAW = json.loads((FIXTURES / "energy" / "halfhourly_J100000.json").read_text())["data"]
KWH = [(row["timestamp"], Decimal(row["kwh"])) for row in RAW]


def _service() -> ReadingService:
    return ReadingService(
        FakePortalClient(FIXTURES), FakeFreshness(), FakeClock(datetime(2026, 11, 4, tzinfo=UTC))
    )


@pytest.mark.anyio
async def test_raw_series_matches_decimal_oracle() -> None:
    result = await _service().get_readings("J100000", None, None, Resolution.RAW)
    assert result.points is not None
    assert len(result.points) == len(RAW) == 337
    assert result.interval_minutes == 30
    assert [p.kwh for p in result.points[1:3]] == [
        float(KWH[1][1] - KWH[0][1]),  # 48439.16 - 48438.74 = 0.42
        float(KWH[2][1] - KWH[1][1]),  # 48439.58 - 48439.16 = 0.42
    ]
    assert result.summary.total_kwh == float(KWH[-1][1] - KWH[0][1])  # 142.05
    assert result.summary.gaps == 0 and result.summary.resets == 0


@pytest.mark.anyio
async def test_daily_bucket_matches_decimal_oracle() -> None:
    # 25/06 = intervals starting on 25/06 = register(26/06 00:00) - register(25/06 00:00)
    by_ts = dict(KWH)
    expected = float(by_ts["26/06/2026 00:00"] - by_ts["25/06/2026 00:00"])
    result = await _service().get_readings("J100000", None, None, Resolution.DAILY)
    assert result.buckets is not None
    bucket = next(b for b in result.buckets if b.start.date() == date(2026, 6, 25))
    assert bucket.kwh == expected
    assert bucket.readings == 48
