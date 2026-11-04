from collections.abc import Sequence
from pathlib import Path

import pytest

from app.domain.exceptions import IndexNotReadyError, NotFoundError
from app.domain.models import Meter, PageResult, Transformer
from app.portal.fake import FakePortalClient
from app.portal.interfaces import PortalPage
from app.services.catalogs.indexed_catalog import IndexedMeterCatalog
from app.services.interfaces import FacetField, MeterFilters
from app.services.transformer_service import TransformerService
from tests.support.fakes import FakeMeterRepository
from tests.support.portal_emulator import FIXTURES

FIXTURES_DIR: Path = FIXTURES


class _NotReadyCatalog:
    """Stands for an empty index: the DT list must still work without meter counts."""

    async def search(self, filters: MeterFilters, page: int, page_size: int) -> PageResult[Meter]:
        raise IndexNotReadyError("the local index is empty; a sync is needed")

    async def facets(
        self, filters: MeterFilters, fields: Sequence[FacetField]
    ) -> dict[FacetField, dict[str, int]]:
        raise IndexNotReadyError("the local index is empty; a sync is needed")


@pytest.fixture
def portal() -> FakePortalClient:
    return FakePortalClient(FIXTURES_DIR)


@pytest.fixture
def service(portal: FakePortalClient) -> TransformerService:
    return TransformerService(portal, _NotReadyCatalog())


@pytest.mark.anyio
async def test_loads_all_pages_sorted(
    service: TransformerService, portal: FakePortalClient
) -> None:
    result = await service.list_transformers(None, 1, 200)
    assert result.total == 40
    codes = [v.transformer.code for v in result.items]
    assert codes == sorted(codes)
    assert len(codes) == 40
    assert [a for n, a in portal.calls if n == "list_transformers"] == [(1,), (2,)]


@pytest.mark.anyio
async def test_filter_by_feeder(service: TransformerService) -> None:
    result = await service.list_transformers("F-001", 1, 50)
    assert result.total == len(result.items) >= 1
    assert all(v.transformer.feeder_code == "F-001" for v in result.items)


@pytest.mark.anyio
async def test_unknown_feeder_is_empty(service: TransformerService) -> None:
    result = await service.list_transformers("F-999", 1, 50)
    assert result.total == 0
    assert list(result.items) == []


@pytest.mark.anyio
async def test_paging_slices_sorted_list(service: TransformerService) -> None:
    everything = await service.list_transformers(None, 1, 200)
    page2 = await service.list_transformers(None, 2, 15)
    assert list(page2.items) == list(everything.items)[15:30]
    assert page2.total == 40
    past = await service.list_transformers(None, 9, 15)
    assert list(past.items) == []
    assert past.total == 40


@pytest.mark.anyio
async def test_get_transformer(service: TransformerService) -> None:
    assert (await service.get_transformer("DT-001")).transformer.name == "Malviya Nagar DT 1"
    with pytest.raises(NotFoundError) as info:
        await service.get_transformer("DT-999")
    assert info.value.message == "transformer DT-999 not found"


class _ShuffledPortal(FakePortalClient):
    """Serves the DT pages in reverse page order and reverse item order."""

    async def list_transformers(self, page: int) -> PortalPage[Transformer]:
        real = await super().list_transformers(3 - page if page in (1, 2) else page)
        return PortalPage(
            items=tuple(reversed(real.items)), total=real.total, page=page, page_size=20
        )


@pytest.mark.anyio
async def test_output_is_sorted_even_when_the_portal_is_not() -> None:
    service = TransformerService(_ShuffledPortal(FIXTURES_DIR), _NotReadyCatalog())
    codes = [v.transformer.code for v in (await service.list_transformers(None, 1, 200)).items]
    assert len(codes) == 40
    assert codes == sorted(codes)
    first = await service.list_transformers(None, 1, 5)
    assert [v.transformer.code for v in first.items] == [
        "DT-001",
        "DT-002",
        "DT-003",
        "DT-004",
        "DT-005",
    ]


@pytest.fixture
async def indexed_service(portal: FakePortalClient) -> TransformerService:
    repo = FakeMeterRepository(await portal.bulk_export())
    return TransformerService(portal, IndexedMeterCatalog(repo))


@pytest.mark.anyio
async def test_meter_count_is_none_while_the_index_is_empty(service: TransformerService) -> None:
    assert (await service.get_transformer("DT-007")).meter_count is None
    assert all(v.meter_count is None for v in (await service.list_transformers(None, 1, 50)).items)


@pytest.mark.anyio
async def test_meter_counts_come_from_the_dt_facet(indexed_service: TransformerService) -> None:
    assert (await indexed_service.get_transformer("DT-007")).meter_count == 13
    listed = (await indexed_service.list_transformers(None, 1, 50)).items
    assert sum(v.meter_count or 0 for v in listed) == 403
    assert all(v.meter_count is not None for v in listed)


@pytest.mark.anyio
async def test_a_dt_without_meters_counts_zero(portal: FakePortalClient) -> None:
    meters = [m for m in await portal.bulk_export() if m.dt_code != "DT-007"]
    service = TransformerService(portal, IndexedMeterCatalog(FakeMeterRepository(meters)))
    assert (await service.get_transformer("DT-007")).meter_count == 0


@pytest.mark.anyio
async def test_list_meters_of_a_dt(indexed_service: TransformerService) -> None:
    page = await indexed_service.list_meters("DT-007", 1, 10)
    assert page.total == 13
    assert len(page.items) == 10
    assert {m.dt_code for m in page.items} == {"DT-007"}
    rest = await indexed_service.list_meters("DT-007", 2, 10)
    assert len(rest.items) == 3


@pytest.mark.anyio
async def test_list_meters_of_an_unknown_dt_is_not_found(
    indexed_service: TransformerService,
) -> None:
    with pytest.raises(NotFoundError):
        await indexed_service.list_meters("DT-999", 1, 10)


@pytest.mark.anyio
async def test_list_meters_with_an_empty_index_is_index_not_ready(
    service: TransformerService,
) -> None:
    with pytest.raises(IndexNotReadyError):
        await service.list_meters("DT-007", 1, 10)
