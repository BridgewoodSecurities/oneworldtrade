from __future__ import annotations

from collections.abc import Sequence
from datetime import datetime
from typing import Protocol

from ..types.fills import BrokerFill
from ..types.orders import OrderRequest
from .models import BrokerAccountIdentity, BrokerOrder


class BrokerClient(Protocol):
    def get_account(self) -> BrokerAccountIdentity: ...

    def submit_order(self, request: OrderRequest) -> BrokerOrder: ...

    def get_order(self, broker_order_id: str) -> BrokerOrder: ...

    def get_order_by_client_order_id(self, client_order_id: str) -> BrokerOrder: ...

    def list_orders(
        self,
        *,
        status: str = "all",
        after: datetime | None = None,
        limit: int = 50,
    ) -> Sequence[BrokerOrder]: ...

    def list_fills(self, broker_order_id: str) -> Sequence[BrokerFill]: ...

    def close(self) -> None: ...
