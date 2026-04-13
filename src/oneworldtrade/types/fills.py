from __future__ import annotations

from datetime import datetime
from decimal import Decimal, ROUND_HALF_UP
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_validator

from .orders import OrderSide


QUANTITY_PRECISION = Decimal("0.000000001")
PRICE_PRECISION = Decimal("0.000001")
FEE_PRECISION = Decimal("0.000001")


def _decimalize(value: Decimal | int | float | str, precision: Decimal) -> Decimal:
    return Decimal(str(value)).quantize(precision, rounding=ROUND_HALF_UP)


class BrokerFill(BaseModel):
    model_config = ConfigDict(arbitrary_types_allowed=False)

    broker_fill_id: str
    broker_order_id: str
    symbol: str
    side: OrderSide
    quantity: Decimal = Field(gt=0)
    price: Decimal = Field(gt=0)
    fees: Decimal = Field(default=Decimal("0"), ge=0)
    executed_at: datetime
    raw: dict[str, Any] = Field(default_factory=dict, repr=False)

    @field_validator("symbol")
    @classmethod
    def _normalize_symbol(cls, value: str) -> str:
        normalized = value.strip().upper()
        if not normalized:
            raise ValueError("symbol is required")
        return normalized

    @field_validator("quantity")
    @classmethod
    def _normalize_quantity(cls, value: Decimal) -> Decimal:
        normalized = _decimalize(value, QUANTITY_PRECISION)
        if normalized <= 0:
            raise ValueError("quantity must be positive")
        return normalized

    @field_validator("price")
    @classmethod
    def _normalize_price(cls, value: Decimal) -> Decimal:
        normalized = _decimalize(value, PRICE_PRECISION)
        if normalized <= 0:
            raise ValueError("price must be positive")
        return normalized

    @field_validator("fees")
    @classmethod
    def _normalize_fees(cls, value: Decimal) -> Decimal:
        normalized = _decimalize(value, FEE_PRECISION)
        if normalized < 0:
            raise ValueError("fees must be non-negative")
        return normalized

