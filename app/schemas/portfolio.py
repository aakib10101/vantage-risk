"""Portfolio and Holding Pydantic schemas."""

from datetime import datetime
from pydantic import BaseModel, field_validator


class HoldingCreate(BaseModel):
    symbol: str
    quantity: float | None = None
    weight: float | None = None

    @field_validator("weight")
    @classmethod
    def weight_range(cls, v):
        if v is not None and not (0 < v <= 1):
            raise ValueError("weight must be in (0, 1]")
        return v

    @field_validator("quantity")
    @classmethod
    def quantity_positive(cls, v):
        if v is not None and v <= 0:
            raise ValueError("quantity must be > 0")
        return v


class HoldingUpdate(BaseModel):
    quantity: float | None = None
    weight: float | None = None


class HoldingResponse(BaseModel):
    id: str
    portfolio_id: str
    symbol: str
    quantity: float | None
    weight: float | None

    model_config = {"from_attributes": True}


class PortfolioCreate(BaseModel):
    name: str
    base_currency: str = "USD"
    benchmark_symbol: str = "^GSPC"
    weighting_mode: str = "weight"

    @field_validator("weighting_mode")
    @classmethod
    def valid_mode(cls, v):
        if v not in ("quantity", "weight"):
            raise ValueError("weighting_mode must be 'quantity' or 'weight'")
        return v


class PortfolioUpdate(BaseModel):
    name: str | None = None
    base_currency: str | None = None
    benchmark_symbol: str | None = None


class PortfolioResponse(BaseModel):
    id: str
    user_id: str
    name: str
    base_currency: str
    benchmark_symbol: str | None
    weighting_mode: str
    holdings: list[HoldingResponse] = []
    created_at: datetime | None = None
    updated_at: datetime | None = None

    model_config = {"from_attributes": True}
