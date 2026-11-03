from typing import Annotated

import pytest
from fastapi import Depends, FastAPI
from fastapi.testclient import TestClient

from app.core.errors import register_error_handlers
from app.core.pagination import DEFAULT_PAGE_SIZE, MAX_PAGE_SIZE, Page, PageParams, paginate
from app.domain.models import PageResult


@pytest.mark.parametrize(
    ("total", "page", "size", "pages", "has_next"),
    [
        (0, 1, 10, 0, False),
        (20, 1, 10, 2, True),
        (20, 2, 10, 2, False),
        (21, 2, 10, 3, True),
        (21, 3, 10, 3, False),
    ],
)
def test_paginate_math(total: int, page: int, size: int, pages: int, has_next: bool) -> None:
    result = paginate(PageResult(items=[1, 2], total=total), page, size)
    assert isinstance(result, Page)
    assert (result.total_pages, result.has_next) == (pages, has_next)
    assert (result.page, result.page_size, result.total, result.items) == (
        page,
        size,
        total,
        [1, 2],
    )


def test_constants() -> None:
    assert (DEFAULT_PAGE_SIZE, MAX_PAGE_SIZE) == (50, 200)


@pytest.fixture
def client() -> TestClient:
    app = FastAPI()
    register_error_handlers(app)

    @app.get("/p")
    def p(params: Annotated[PageParams, Depends()]) -> dict[str, int]:
        return {"page": params.page, "page_size": params.page_size}

    return TestClient(app)


def test_defaults(client: TestClient) -> None:
    assert client.get("/p").json() == {"page": 1, "page_size": 50}


@pytest.mark.parametrize("qs", ["page_size=201", "page_size=0", "page=0"])
def test_out_of_range_is_422_envelope(client: TestClient, qs: str) -> None:
    r = client.get(f"/p?{qs}")
    assert r.status_code == 422
    body = r.json()["error"]
    assert body["code"] == "validation_error"
    assert set(body["details"]["errors"][0]) == {"loc", "msg", "type"}


@pytest.mark.parametrize("size", [0, -1])
def test_paginate_rejects_non_positive_page_size(size: int) -> None:
    with pytest.raises(ValueError, match="page_size"):
        paginate(PageResult(items=[], total=0), 1, size)
