from __future__ import annotations

import time
from dataclasses import dataclass

from ..broker.base import BrokerClient
from ..broker.models import BrokerOrder


@dataclass(slots=True)
class OrderLifecycleSnapshot:
    order: BrokerOrder
    timed_out: bool
    poll_count: int


def wait_for_terminal_order(
    broker: BrokerClient,
    broker_order_id: str,
    *,
    poll_interval_seconds: float,
    timeout_seconds: float,
) -> OrderLifecycleSnapshot:
    order = broker.get_order(broker_order_id)
    poll_count = 1
    if order.is_terminal:
        return OrderLifecycleSnapshot(
            order=order,
            timed_out=False,
            poll_count=poll_count,
        )

    deadline = time.monotonic() + timeout_seconds
    while time.monotonic() < deadline:
        time.sleep(poll_interval_seconds)
        order = broker.get_order(broker_order_id)
        poll_count += 1
        if order.is_terminal:
            return OrderLifecycleSnapshot(
                order=order,
                timed_out=False,
                poll_count=poll_count,
            )

    return OrderLifecycleSnapshot(order=order, timed_out=True, poll_count=poll_count)

