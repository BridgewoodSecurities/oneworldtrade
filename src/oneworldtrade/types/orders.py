from __future__ import annotations

from decimal import Decimal, ROUND_HALF_UP
from enum import Enum

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


QUANTITY_PRECISION = Decimal("0.000000001")
PRICE_PRECISION = Decimal("0.000001")


def _decimalize(value: Decimal | int | float | str, precision: Decimal) -> Decimal:
    return Decimal(str(value)).quantize(precision, rounding=ROUND_HALF_UP)


class OrderSide(str, Enum):
    BUY = "buy"
    SELL = "sell"


class OrderType(str, Enum):
    MARKET = "market"
    LIMIT = "limit"


class TimeInForce(str, Enum):
    DAY = "day"
    GTC = "gtc"
    IOC = "ioc"
    FOK = "fok"
    OPG = "opg"
    CLS = "cls"


class OrderRequest(BaseModel):
    model_config = ConfigDict(frozen=True)

    symbol: str
    side: OrderSide
    qty: Decimal = Field(gt=0)
    order_type: OrderType = OrderType.MARKET
    time_in_force: TimeInForce = TimeInForce.DAY
    limit_price: Decimal | None = None
    extended_hours: bool = False
    client_order_id: str | None = None

    @field_validator("symbol")
    @classmethod
    def _normalize_symbol(cls, value: str) -> str:
        normalized = value.strip().upper()
        if not normalized:
            raise ValueError("symbol is required")
        return normalized

    @field_validator("qty")
    @classmethod
    def _normalize_qty(cls, value: Decimal) -> Decimal:
        normalized = _decimalize(value, QUANTITY_PRECISION)
        if normalized <= 0:
            raise ValueError("qty must be positive")
        return normalized

    @field_validator("limit_price")
    @classmethod
    def _normalize_limit_price(cls, value: Decimal | None) -> Decimal | None:
        if value is None:
            return None
        normalized = _decimalize(value, PRICE_PRECISION)
        if normalized <= 0:
            raise ValueError("limit_price must be positive")
        return normalized

    @field_validator("client_order_id")
    @classmethod
    def _normalize_client_order_id(cls, value: str | None) -> str | None:
        if value is None:
            return None
        normalized = value.strip()
        if not normalized:
            return None
        if len(normalized) > 128:
            raise ValueError("client_order_id must be 128 characters or fewer")
        return normalized

    @model_validator(mode="after")
    def _validate_order_shape(self) -> "OrderRequest":
        if self.order_type == OrderType.LIMIT and self.limit_price is None:
            raise ValueError("limit_price is required for limit orders")
        if self.order_type == OrderType.MARKET and self.limit_price is not None:
            raise ValueError("limit_price is only allowed for limit orders")
        if self.extended_hours and not (
            self.order_type == OrderType.LIMIT
            and self.time_in_force == TimeInForce.DAY
        ):
            raise ValueError(
                "extended_hours is only supported for DAY limit orders"
            )
        return self

