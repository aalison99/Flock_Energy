from pathlib import Path

import pytest

from app.domain.exceptions import NotFoundError
from app.domain.models import Transformer
from app.portal.fake import FakePortalClient
from app.portal.interfaces import PortalPage
from app.services.transformer_service import TransformerService
from tests.support.portal_emulator import FIXTURES

FIXTURES_DIR: Path = FIXTURES


@pytest.fixture
def portal() -> FakePortalClient:
    return FakePortalClient(FIXTURES_DIR)


@pytest.fixture
def service(portal: FakePortalClient) -> TransformerService:
    return TransformerService(portal)


@pytest.mark.anyio
async def test_loads_all_pages_sorted(
    service: TransformerService, portal: FakePortalClient
) -> None:
    result = await service.list_transformers(None, 1, 200)
    assert result.total == 40
    codes = [t.code for t in result.items]
    assert codes == sorted(codes)
    assert len(codes) == 40
    assert [a for n, a in portal.calls if n == "list_transformers"] == [(1,), (2,)]


@pytest.mark.anyio
async def test_filter_by_feeder(service: TransformerService) -> None:
    result = await service.list_transformers("F-001", 1, 50)
    assert result.total == len(result.items) >= 1
    assert all(t.feeder_code == "F-001" for t in result.items)


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
    assert (await service.get_transformer("DT-001")).name == "Malviya Nagar DT 1"
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
    service = TransformerService(_ShuffledPortal(FIXTURES_DIR))
    codes = [t.code for t in (await service.list_transformers(None, 1, 200)).items]
    assert len(codes) == 40
    assert codes == sorted(codes)
    first = await service.list_transformers(None, 1, 5)
    assert [t.code for t in first.items] == ["DT-001", "DT-002", "DT-003", "DT-004", "DT-005"]
