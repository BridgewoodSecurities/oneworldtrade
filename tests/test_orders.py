from __future__ import annotations

from decimal import Decimal

import pytest

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

