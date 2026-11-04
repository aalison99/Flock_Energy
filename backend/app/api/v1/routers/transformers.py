"""Transformer (DT) endpoints: list and detail."""

from typing import Annotated

from fastapi import APIRouter, Depends, Path, Query

from app.api.v1.schemas.common import error_responses
from app.api.v1.schemas.meters import MeterSummary, to_meter_summary
from app.api.v1.schemas.transformers import TransformerOut, to_transformer_out
from app.core.deps import get_transformer_service
from app.core.pagination import Page, PageParams, paginate
from app.domain.models import PageResult
from app.services.transformer_service import TransformerService

router = APIRouter(tags=["transformers"])


@router.get(
    "/transformers",
    operation_id="listTransformers",
    response_model=Page[TransformerOut],
    summary="List transformers",
    description="Paginated transformers sorted by code, optionally filtered by feeder.",
    responses=error_responses(422, 502, 503),
)
async def list_transformers(
    service: Annotated[TransformerService, Depends(get_transformer_service)],
    params: Annotated[PageParams, Depends()],
    feeder: Annotated[
        str | None,
        Query(pattern=r"^F-\d{3}$", description="Only transformers on this feeder, e.g. F-001."),
    ] = None,
) -> Page[TransformerOut]:
    result = await service.list_transformers(feeder, params.page, params.page_size)
    items = PageResult(items=[to_transformer_out(t) for t in result.items], total=result.total)
    return paginate(items, params.page, params.page_size)


@router.get(
    "/transformers/{code}",
    operation_id="getTransformer",
    response_model=TransformerOut,
    summary="Get a transformer",
    description="One transformer by its code.",
    responses=error_responses(404, 422, 502, 503),
)
async def get_transformer(
    service: Annotated[TransformerService, Depends(get_transformer_service)],
    code: Annotated[str, Path(pattern=r"^DT-\d{3}$", description="Transformer code, e.g. DT-001.")],
) -> TransformerOut:
    return to_transformer_out(await service.get_transformer(code))


@router.get(
    "/transformers/{code}/meters",
    operation_id="listTransformerMeters",
    response_model=Page[MeterSummary],
    summary="List a transformer's meters",
    description="Paginated meters installed on one transformer. Needs the local index.",
    responses=error_responses(404, 409, 422, 502, 503),
)
async def list_transformer_meters(
    service: Annotated[TransformerService, Depends(get_transformer_service)],
    params: Annotated[PageParams, Depends()],
    code: Annotated[str, Path(pattern=r"^DT-\d{3}$", description="Transformer code, e.g. DT-001.")],
) -> Page[MeterSummary]:
    result = await service.list_meters(code, params.page, params.page_size)
    summaries = PageResult(items=[to_meter_summary(m) for m in result.items], total=result.total)
    return paginate(summaries, params.page, params.page_size)
