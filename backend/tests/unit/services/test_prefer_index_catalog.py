import pytest

from app.domain.exceptions import IndexNotReadyError, NotFoundError
from app.domain.models import Meter, PageResult
from app.portal.fake import FakePortalClient
from app.services.catalogs.indexed_catalog import IndexedMeterCatalog
from app.services.catalogs.live_catalog import LiveMeterCatalog
from app.services.catalogs.prefer_index import PreferIndexCatalog
from app.services.interfaces import FacetField, MeterFilters
from tests.support.fakes import FakeMeterRepository
from tests.support.portal_emulator import FIXTURES

pytestmark = pytest.mark.anyio


async def _catalog(ready: bool) -> tuple[PreferIndexCatalog, FakePortalClient]:
    portal = FakePortalClient(FIXTURES)
    meters = await portal.bulk_export() if ready else []
    repo = FakeMeterRepository(meters)
    portal.calls.clear()
    return PreferIndexCatalog(IndexedMeterCatalog(repo), LiveMeterCatalog(portal)), portal


async def test_empty_index_falls_back_to_the_portal_for_search_and_get() -> None:
    catalog, portal = await _catalog(ready=False)
    page = await catalog.search(MeterFilters(q="se33962"), 1, 10)
    assert page.total == 1
    hit = await catalog.get("J100000")
    assert hit.source == "portal"
    assert [name for name, _ in portal.calls] == ["list_meters", "get_meter"]


async def test_ready_index_is_used_and_the_portal_untouched() -> None:
    catalog, portal = await _catalog(ready=True)
    assert (await catalog.search(MeterFilters(q="se33962"), 1, 10)).total == 1
    assert (await catalog.get("J100000")).source == "index"
    assert portal.calls == []


async def test_ready_index_serves_filters_the_portal_cannot() -> None:
    catalog, _ = await _catalog(ready=True)
    assert (await catalog.search(MeterFilters(dt="DT-007"), 1, 50)).total == 13


async def test_empty_index_with_a_filter_only_the_index_serves_is_index_not_ready() -> None:
    catalog, portal = await _catalog(ready=False)
    with pytest.raises(IndexNotReadyError, match="local index is empty"):
        await catalog.search(MeterFilters(dt="DT-007"), 1, 50)
    assert portal.calls == []


async def test_a_plain_validation_error_from_live_is_not_masked() -> None:
    from app.domain.exceptions import ValidationError

    class BrokenLive(LiveMeterCatalog):
        async def search(
            self, filters: MeterFilters, page: int, page_size: int
        ) -> PageResult[Meter]:
            raise ValidationError("portal said no")

    portal = FakePortalClient(FIXTURES)
    catalog = PreferIndexCatalog(IndexedMeterCatalog(FakeMeterRepository()), BrokenLive(portal))
    with pytest.raises(ValidationError, match="portal said no") as info:
        await catalog.search(MeterFilters(), 1, 10)
    assert not isinstance(info.value, IndexNotReadyError)


async def test_facets_on_an_empty_index_raise_index_not_ready() -> None:
    catalog, _ = await _catalog(ready=False)
    with pytest.raises(IndexNotReadyError):
        await catalog.facets(MeterFilters(), [FacetField.STATUS])


async def test_ready_index_facets() -> None:
    catalog, _ = await _catalog(ready=True)
    result = await catalog.facets(MeterFilters(), [FacetField.PHASE])
    assert result == {FacetField.PHASE: {"single": 277, "three": 126}}


async def test_not_found_in_a_ready_index_does_not_fall_back() -> None:
    catalog, portal = await _catalog(ready=True)
    with pytest.raises(NotFoundError):
        await catalog.get("J999999")
    assert portal.calls == []
