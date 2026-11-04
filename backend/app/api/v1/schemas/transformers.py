"""Transformer response schema."""

from pydantic import BaseModel, ConfigDict, Field

from app.domain.models import Transformer


class TransformerOut(BaseModel):
    """A distribution transformer (DT)."""

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "code": "DT-001",
                "name": "Malviya Nagar DT 1",
                "feeder_code": "F-001",
                "capacity_kva": 100,
            }
        }
    )

    code: str = Field(description="Transformer code, e.g. DT-001.")
    name: str = Field(description="Transformer display name.")
    feeder_code: str | None = Field(description="Code of the feeder it hangs off, if known.")
    capacity_kva: int = Field(description="Rated capacity in kVA.")


def to_transformer_out(transformer: Transformer) -> TransformerOut:
    return TransformerOut(
        code=transformer.code,
        name=transformer.name,
        feeder_code=transformer.feeder_code,
        capacity_kva=transformer.capacity_kva,
    )
