from __future__ import annotations

from datetime import timezone
from decimal import Decimal
from uuid import uuid4

from ..bridgewood.models import BridgewoodExecution
from ..broker.models import BrokerOrder
from ..exceptions import BridgewoodError
from ..types.fills import BrokerFill
from ..types.reporting import BridgewoodReportingMode


def build_client_order_id(prefix: str = "owt") -> str:
    return f"{prefix}-{uuid4().hex[:24]}"


def external_order_id_for_order(order: BrokerOrder) -> str:
    return order.order_id


def external_order_id_for_fill(order: BrokerOrder, fill: BrokerFill) -> str:
    return f"{order.order_id}:fill:{fill.broker_fill_id}"


def bridgewood_execution_from_order(
    order: BrokerOrder,
    fills: list[BrokerFill],
) -> BridgewoodExecution:
    if not order.is_filled:
        raise BridgewoodError(
            f"Cannot build a Bridgewood execution for non-filled order {order.order_id}."
        )
    quantity = order.filled_qty if order.filled_qty > 0 else order.qty
    if quantity <= 0:
        raise BridgewoodError(
            f"Filled Alpaca order {order.order_id} is missing a positive filled quantity."
        )
    if order.filled_avg_price is None:
        raise BridgewoodError(
            f"Filled Alpaca order {order.order_id} is missing filled_avg_price."
        )
    executed_at = order.filled_at
    if executed_at is None and fills:
        executed_at = max(fill.executed_at for fill in fills)
    if executed_at is None:
        raise BridgewoodError(
            f"Filled Alpaca order {order.order_id} is missing filled_at and no fills were available."
        )
    fees = sum((fill.fees for fill in fills), Decimal("0"))
    normalized_timestamp = executed_at.astimezone(timezone.utc)
    return BridgewoodExecution(
        external_order_id=external_order_id_for_order(order),
        symbol=order.symbol,
        side=order.side,
        quantity=quantity,
        price=order.filled_avg_price,
        fees=fees,
        executed_at=normalized_timestamp,
    )


def bridgewood_executions_from_order(
    order: BrokerOrder,
    fills: list[BrokerFill],
    *,
    mode: BridgewoodReportingMode,
) -> list[BridgewoodExecution]:
    if mode == BridgewoodReportingMode.AGGREGATED_ORDER:
        return [bridgewood_execution_from_order(order, fills)]

    if fills:
        sorted_fills = sorted(fills, key=lambda fill: fill.executed_at)
        return [
            BridgewoodExecution(
                external_order_id=external_order_id_for_fill(order, fill),
                symbol=fill.symbol,
                side=fill.side,
                quantity=fill.quantity,
                price=fill.price,
                fees=fill.fees,
                executed_at=fill.executed_at.astimezone(timezone.utc),
            )
            for fill in sorted_fills
        ]

    return [bridgewood_execution_from_order(order, fills)]
