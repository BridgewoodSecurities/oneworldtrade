from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field

from ..bridgewood.models import BridgewoodExecution, BridgewoodExecutionReportResult
from ..broker.models import BrokerOrder
from .fills import BrokerFill
from .orders import OrderRequest


class TradeResult(BaseModel):
    model_config = ConfigDict(arbitrary_types_allowed=False)

    order_request: OrderRequest
    broker_order_id: str | None = None
    broker_order: BrokerOrder | None = None
    fills: list[BrokerFill] = Field(default_factory=list)
    wait_for_fill: bool = True
    timed_out: bool = False
    report_requested: bool = True
    report_attempted: bool = False
    report_succeeded: bool = False
    report_errors: list[str] = Field(default_factory=list)
    bridgewood_execution: BridgewoodExecution | None = None
    bridgewood_results: list[BridgewoodExecutionReportResult] = Field(
        default_factory=list
    )
    retriable: bool = False

    @property
    def broker_status(self) -> str | None:
        if self.broker_order is None:
            return None
        return self.broker_order.status.value

    @property
    def terminal(self) -> bool:
        return bool(self.broker_order and self.broker_order.is_terminal)

    @property
    def filled(self) -> bool:
        return bool(self.broker_order and self.broker_order.is_filled)


class ReconciliationResult(BaseModel):
    checked_orders: int = 0
    attempted_reports: int = 0
    successful_reports: int = 0
    duplicate_reports: int = 0
    failed_reports: int = 0
    results: list[TradeResult] = Field(default_factory=list)
