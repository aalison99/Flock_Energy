"""Transformer use cases, served from the portal's (cached) DT list."""

from app.domain.exceptions import NotFoundError
from app.domain.models import PageResult, Transformer
from app.portal.interfaces import PortalClient

_PORTAL_PAGE_SIZE = 20


class TransformerService:
    def __init__(self, portal: PortalClient) -> None:
        self._portal = portal

    async def _all(self) -> list[Transformer]:
        found: list[Transformer] = []
        page = 1
        while True:
            result = await self._portal.list_transformers(page)
            found.extend(result.items)
            if len(result.items) < _PORTAL_PAGE_SIZE or len(found) >= result.total:
                return found
            page += 1

    async def list_transformers(
        self, feeder: str | None, page: int, page_size: int
    ) -> PageResult[Transformer]:
        matching = [t for t in await self._all() if feeder is None or t.feeder_code == feeder]
        matching.sort(key=lambda t: t.code)
        start = (page - 1) * page_size
        return PageResult(items=matching[start : start + page_size], total=len(matching))

    async def get_transformer(self, code: str) -> Transformer:
        for transformer in await self._all():
            if transformer.code == code:
                return transformer
        raise NotFoundError(f"transformer {code} not found")
