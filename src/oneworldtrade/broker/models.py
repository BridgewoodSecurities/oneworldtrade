from __future__ import annotations

from datetime import datetime
from decimal import Decimal, ROUND_HALF_UP
from enum import Enum
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_validator

from ..types.orders import OrderSide, OrderType, TimeInForce


QUANTITY_PRECISION = Decimal("0.000000001")
PRICE_PRECISION = Decimal("0.000001")


def _decimalize(
    value: Decimal | int | float | str | None,
    precision: Decimal,
) -> Decimal | None:
    if value is None:
        return None
    return Decimal(str(value)).quantize(precision, rounding=ROUND_HALF_UP)


class BrokerOrderStatus(str, Enum):
    NEW = "new"
    PARTIALLY_FILLED = "partially_filled"
    FILLED = "filled"
    DONE_FOR_DAY = "done_for_day"
    CANCELED = "canceled"
    EXPIRED = "expired"
    REPLACED = "replaced"
    PENDING_CANCEL = "pending_cancel"
    PENDING_REPLACE = "pending_replace"
    ACCEPTED = "accepted"
    PENDING_NEW = "pending_new"
    ACCEPTED_FOR_BIDDING = "accepted_for_bidding"
    STOPPED = "stopped"
    REJECTED = "rejected"
    SUSPENDED = "suspended"
    CALCULATED = "calculated"


TERMINAL_ORDER_STATUSES = {
    BrokerOrderStatus.FILLED,
    BrokerOrderStatus.CANCELED,
    BrokerOrderStatus.EXPIRED,
    BrokerOrderStatus.REPLACED,
    BrokerOrderStatus.REJECTED,
    BrokerOrderStatus.SUSPENDED,
}


class BrokerAccountIdentity(BaseModel):
    model_config = ConfigDict(arbitrary_types_allowed=False)

    account_id: str
    account_number: str | None = None
    status: str | None = None
    currency: str | None = None
    buying_power: Decimal | None = None
    raw: dict[str, Any] = Field(default_factory=dict, repr=False)

    @field_validator("buying_power")
    @classmethod
    def _normalize_buying_power(cls, value: Decimal | None) -> Decimal | None:
        return _decimalize(value, PRICE_PRECISION)


class BrokerOrder(BaseModel):
    model_config = ConfigDict(arbitrary_types_allowed=False)

    broker_name: str
    order_id: str
    client_order_id: str | None = None
    symbol: str
    side: OrderSide
    order_type: OrderType
    time_in_force: TimeInForce
    status: BrokerOrderStatus
    qty: Decimal
    filled_qty: Decimal = Decimal("0")
    filled_avg_price: Decimal | None = None
    limit_price: Decimal | None = None
    extended_hours: bool = False
    created_at: datetime | None = None
    submitted_at: datetime | None = None
    filled_at: datetime | None = None
    canceled_at: datetime | None = None
    expired_at: datetime | None = None
    failed_at: datetime | None = None
    raw: dict[str, Any] = Field(default_factory=dict, repr=False)

    @field_validator("symbol")
    @classmethod
    def _normalize_symbol(cls, value: str) -> str:
        normalized = value.strip().upper()
        if not normalized:
            raise ValueError("symbol is required")
        return normalized

    @field_validator("qty", "filled_qty")
    @classmethod
    def _normalize_qty(cls, value: Decimal) -> Decimal:
        normalized = _decimalize(value, QUANTITY_PRECISION)
        if normalized is None or normalized < 0:
            raise ValueError("quantity values must be non-negative")
        return normalized

    @field_validator("filled_avg_price", "limit_price")
    @classmethod
    def _normalize_price(cls, value: Decimal | None) -> Decimal | None:
        if value is None:
            return None
        normalized = _decimalize(value, PRICE_PRECISION)
        if normalized is None or normalized <= 0:
            raise ValueError("price values must be positive")
        return normalized

    @property
    def is_terminal(self) -> bool:
        return self.status in TERMINAL_ORDER_STATUSES

    @property
    def is_filled(self) -> bool:
        return self.status == BrokerOrderStatus.FILLED

