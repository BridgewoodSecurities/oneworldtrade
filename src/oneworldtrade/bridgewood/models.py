from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal, ROUND_HALF_UP
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

from ..types.orders import OrderSide


QUANTITY_PRECISION = Decimal("0.000000001")
PRICE_PRECISION = Decimal("0.000001")


def _decimalize(value: Decimal | int | float | str, precision: Decimal) -> Decimal:
    return Decimal(str(value)).quantize(precision, rounding=ROUND_HALF_UP)


class BridgewoodExecution(BaseModel):
    model_config = ConfigDict(arbitrary_types_allowed=False)

    external_order_id: str
    symbol: str
    side: OrderSide
    quantity: Decimal = Field(gt=0)
    price: Decimal = Field(gt=0)
    fees: Decimal = Field(default=Decimal("0"), ge=0)
    executed_at: datetime

    @field_validator("external_order_id")
    @classmethod
    def _normalize_external_order_id(cls, value: str) -> str:
        normalized = value.strip()
        if not normalized:
            raise ValueError("external_order_id is required")
        return normalized

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

    @field_validator("price", "fees")
    @classmethod
    def _normalize_price_like(cls, value: Decimal) -> Decimal:
        normalized = _decimalize(value, PRICE_PRECISION)
        if normalized < 0:
            raise ValueError("price-like values must be non-negative")
        return normalized

    def to_payload(self) -> dict[str, object]:
        return {
            "external_order_id": self.external_order_id,
            "symbol": self.symbol,
            "side": self.side.value,
            "quantity": float(self.quantity),
            "price": float(self.price),
            "fees": float(self.fees),
            "executed_at": self.executed_at.astimezone(timezone.utc)
            .isoformat()
            .replace("+00:00", "Z")
            if self.executed_at.tzinfo
            else self.executed_at.isoformat() + "Z",
        }


class BridgewoodExecutionReportResult(BaseModel):
    external_order_id: str
    status: Literal["recorded", "duplicate"]
    execution_id: str | None = None
    symbol: str
    side: str
    quantity: float
    price_per_share: float
    gross_notional: float
    fees: float
    executed_at: datetime


class BridgewoodPosition(BaseModel):
    symbol: str
    quantity: float
    market_value: float
    avg_cost: float


class BridgewoodPortfolio(BaseModel):
    agent_id: str
    cash: float
    total_value: float
    pnl: float
    return_pct: float
    positions: list[BridgewoodPosition]


class BridgewoodExecutionReportResponse(BaseModel):
    results: list[BridgewoodExecutionReportResult]
    portfolio_after: BridgewoodPortfolio


class BridgewoodAgentIdentity(BaseModel):
    agent_id: str
    user_id: str
    name: str
    icon_url: str | None = None
    starting_cash: float
    trading_mode: str
