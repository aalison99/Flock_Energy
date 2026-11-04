"""Pagination: the Page response model, the paginate() helper and the PageParams dependency."""

import math

from fastapi import Query
from pydantic import BaseModel, Field

from app.domain.models import PageResult

DEFAULT_PAGE_SIZE = 50
MAX_PAGE_SIZE = 200


class Page[T](BaseModel):
    """A page of items with navigation metadata."""

    items: list[T] = Field(description="The items on this page.")
    page: int = Field(description="Current page number, starting at 1.")
    page_size: int = Field(description="Maximum items per page.")
    total: int = Field(description="Total number of matching items.")
    total_pages: int = Field(description="Total number of pages at this page size.")
    has_next: bool = Field(description="Whether a later page exists.")


class PageParams:
    """FastAPI dependency parsing the `page` and `page_size` query parameters."""

    def __init__(
        self,
        page: int = Query(1, ge=1, description="Page number, starting at 1."),
        page_size: int = Query(
            DEFAULT_PAGE_SIZE, ge=1, le=MAX_PAGE_SIZE, description="Items per page (1 to 200)."
        ),
    ) -> None:
        self.page = page
        self.page_size = page_size


def paginate[T](result: PageResult[T], page: int, page_size: int) -> Page[T]:
    """Wrap a PageResult in a Page for the given page number and size."""
    if page_size < 1:
        raise ValueError("page_size must be >= 1")
    total_pages = math.ceil(result.total / page_size)
    return Page[T](
        items=list(result.items),
        page=page,
        page_size=page_size,
        total=result.total,
        total_pages=total_pages,
        has_next=page < total_pages,
    )
