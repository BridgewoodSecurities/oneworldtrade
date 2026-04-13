from __future__ import annotations

from datetime import datetime
from decimal import Decimal

import pytest

from oneworldtrade.bridgewood.models import BridgewoodExecution
from oneworldtrade.types.fills import BrokerFill
from oneworldtrade.types.orders import OrderRequest, OrderSide, OrderType


def test_limit_order_requires_limit_price() -> None:
    with pytest.raises(ValueError, match="limit_price is required"):
        OrderRequest(
            symbol="AAPL",
            side=OrderSide.BUY,
            qty=Decimal("1"),
            order_type=OrderType.LIMIT,
        )


def test_market_order_disallows_limit_price() -> None:
    with pytest.raises(ValueError, match="limit_price is only allowed"):
        OrderRequest(
            symbol="AAPL",
            side=OrderSide.BUY,
            qty=Decimal("1"),
            order_type=OrderType.MARKET,
            limit_price=Decimal("180"),
        )


def test_bridgewood_execution_rejects_naive_timestamps() -> None:
    with pytest.raises(ValueError, match="timezone-aware"):
        BridgewoodExecution(
            external_order_id="order-1",
            symbol="AAPL",
            side=OrderSide.BUY,
            quantity=Decimal("1"),
            price=Decimal("187.52"),
            fees=Decimal("0"),
            executed_at=datetime(2026, 4, 13, 15, 45),
        )


def test_broker_fill_rejects_naive_timestamps() -> None:
    with pytest.raises(ValueError, match="timezone-aware"):
        BrokerFill(
            broker_fill_id="fill-1",
            broker_order_id="order-1",
            symbol="AAPL",
            side=OrderSide.BUY,
            quantity=Decimal("1"),
            price=Decimal("187.52"),
            fees=Decimal("0"),
            executed_at=datetime(2026, 4, 13, 15, 45),
        )
