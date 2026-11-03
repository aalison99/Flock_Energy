"""FakePortalClient extras: failure injection, call log, closed flag."""

from pathlib import Path

import pytest

from app.domain.exceptions import UpstreamUnavailableError
from app.portal.fake import FakePortalClient

FIX = Path(__file__).parents[2] / "fixtures" / "portal"
pytestmark = pytest.mark.anyio


async def test_next_call_fails_once() -> None:
    fake = FakePortalClient(FIX)
    fake.fail("get_meter", UpstreamUnavailableError("down"))
    with pytest.raises(UpstreamUnavailableError):
        await fake.get_meter("J100000")
    assert (await fake.get_meter("J100000")).meter_id == "J100000"


async def test_times_and_on_call() -> None:
    fake = FakePortalClient(FIX)
    fake.fail("get_geo", UpstreamUnavailableError("down"), on_call=2, times=2)
    assert await fake.get_geo("J100000") is not None
    for _ in range(2):
        with pytest.raises(UpstreamUnavailableError):
            await fake.get_geo("J100000")
    assert await fake.get_geo("J100000") is not None


async def test_failures_are_per_method() -> None:
    fake = FakePortalClient(FIX)
    fake.fail("bulk_export", UpstreamUnavailableError("down"), times=3)
    assert (await fake.get_meter("J100000")).meter_id == "J100000"
    with pytest.raises(UpstreamUnavailableError):
        await fake.bulk_export()


async def test_call_log_and_close() -> None:
    fake = FakePortalClient(FIX)
    await fake.list_meters(2, "x")
    await fake.get_meter("J100000")
    assert fake.calls == [("list_meters", (2, "x")), ("get_meter", ("J100000",))]
    assert not fake.closed
    await fake.aclose()
    await fake.aclose()
    assert fake.closed


async def test_later_transformer_pages_empty() -> None:
    page = await FakePortalClient(FIX).list_transformers(3)
    assert page.items == () and page.total == 40
