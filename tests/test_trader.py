from __future__ import annotations

from collections.abc import Sequence
from datetime import datetime, timedelta, timezone
from decimal import Decimal

import pytest

from oneworldtrade.bridgewood.models import (
    BridgewoodAgentIdentity,
    BridgewoodExecution,
    BridgewoodExecutionReportResponse,
    BridgewoodExecutionReportResult,
    BridgewoodPortfolio,
    BridgewoodPosition,
)
from oneworldtrade.broker.models import (
    BrokerAccountIdentity,
    BrokerOrder,
    BrokerOrderStatus,
)
from oneworldtrade.config import OneWorldTradeConfig
from oneworldtrade.exceptions import BridgewoodError, ConfigurationError
from oneworldtrade.execution.trader import Trader
from oneworldtrade.types.fills import BrokerFill
from oneworldtrade.types.orders import OrderRequest, OrderSide, OrderType, TimeInForce
from oneworldtrade.types.reporting import BridgewoodReportingMode


UTC = timezone.utc


def _order(
    *,
    order_id: str,
    status: BrokerOrderStatus,
    created_at: datetime | None = None,
    filled_at: datetime | None = None,
    filled_qty: Decimal = Decimal("1"),
) -> BrokerOrder:
    return BrokerOrder(
        broker_name="fake-broker",
        order_id=order_id,
        client_order_id=f"client-{order_id}",
        symbol="AAPL",
        side=OrderSide.BUY,
        order_type=OrderType.MARKET,
        time_in_force=TimeInForce.DAY,
        status=status,
        qty=Decimal("1"),
        filled_qty=filled_qty,
        filled_avg_price=(
            Decimal("187.52") if status == BrokerOrderStatus.FILLED else None
        ),
        created_at=created_at or datetime(2026, 4, 13, 15, 30, tzinfo=UTC),
        filled_at=filled_at,
    )


def _fill(order_id: str, fill_id: str = "fill-1") -> BrokerFill:
    return BrokerFill(
        broker_fill_id=fill_id,
        broker_order_id=order_id,
        symbol="AAPL",
        side=OrderSide.BUY,
        quantity=Decimal("1"),
        price=Decimal("187.52"),
        fees=Decimal("0"),
        executed_at=datetime(2026, 4, 13, 15, 45, tzinfo=UTC),
    )


def _report_response(status: str) -> BridgewoodExecutionReportResponse:
    return BridgewoodExecutionReportResponse(
        results=[
            BridgewoodExecutionReportResult(
                external_order_id="alpaca-order-1",
                status=status,
                execution_id="exec-1" if status == "recorded" else None,
                symbol="AAPL",
                side="buy",
                quantity=1.0,
                price_per_share=187.52,
                gross_notional=187.52,
                fees=0.0,
                executed_at=datetime(2026, 4, 13, 15, 45, tzinfo=UTC),
            )
        ],
        portfolio_after=BridgewoodPortfolio(
            agent_id="agent-1",
            cash=9812.48,
            total_value=10000.0,
            pnl=0.0,
            return_pct=0.0,
            positions=[
                BridgewoodPosition(
                    symbol="AAPL",
                    quantity=1.0,
                    market_value=187.52,
                    avg_cost=187.52,
                )
            ],
        ),
    )


class FakeBroker:
    def __init__(
        self,
        *,
        submitted_order: BrokerOrder,
        get_order_sequence: Sequence[BrokerOrder] | None = None,
        fills: dict[str, list[BrokerFill]] | None = None,
        listed_orders: Sequence[BrokerOrder] | None = None,
    ) -> None:
        self.submitted_order = submitted_order
        self.get_order_sequence = list(get_order_sequence or [submitted_order])
        self.fills = fills or {}
        self.listed_orders = list(listed_orders or [])
        self.submitted_requests: list[OrderRequest] = []

    def get_account(self) -> BrokerAccountIdentity:
        return BrokerAccountIdentity(account_id="broker-account-1", status="ACTIVE")

    def submit_order(self, request: OrderRequest) -> BrokerOrder:
        self.submitted_requests.append(request)
        return self.submitted_order

    def get_order(self, broker_order_id: str) -> BrokerOrder:
        for order in self.listed_orders:
            if order.order_id == broker_order_id:
                return order
        if len(self.get_order_sequence) > 1:
            return self.get_order_sequence.pop(0)
        return self.get_order_sequence[0]

    def get_order_by_client_order_id(self, client_order_id: str) -> BrokerOrder:
        return self.submitted_order

    def list_orders(
        self,
        *,
        status: str = "all",
        after: datetime | None = None,
        limit: int = 50,
    ) -> Sequence[BrokerOrder]:
        del status, after, limit
        return self.listed_orders

    def list_fills(self, broker_order_id: str) -> Sequence[BrokerFill]:
        return self.fills.get(broker_order_id, [])

    def close(self) -> None:
        return None


class FakeBridgewood:
    def __init__(
        self,
        *,
        responses: Sequence[BridgewoodExecutionReportResponse] | None = None,
        errors: Sequence[BridgewoodError] | None = None,
    ) -> None:
        self.responses = list(responses or [])
        self.errors = list(errors or [])
        self.reported: list[list[BridgewoodExecution]] = []

    def get_me(self) -> BridgewoodAgentIdentity:
        return BridgewoodAgentIdentity(
            agent_id="agent-1",
            user_id="user-1",
            name="Momentum Bot",
            starting_cash=10000.0,
            trading_mode="paper",
        )

    def get_portfolio(self) -> BridgewoodPortfolio:
        return _report_response("recorded").portfolio_after

    def get_prices(self, symbols: list[str]) -> dict[str, object]:
        return {"prices": {symbol: 100.0 for symbol in symbols}}

    def report_executions(
        self,
        executions: list[BridgewoodExecution],
    ) -> BridgewoodExecutionReportResponse:
        self.reported.append(executions)
        if self.errors:
            raise self.errors.pop(0)
        if self.responses:
            return self.responses.pop(0)
        return _report_response("recorded")

    def close(self) -> None:
        return None


def _config(
    max_attempts: int = 3,
    reporting_mode: BridgewoodReportingMode = BridgewoodReportingMode.AGGREGATED_ORDER,
) -> OneWorldTradeConfig:
    return OneWorldTradeConfig.model_construct(
        alpaca_api_key="alpaca-key",
        alpaca_secret_key="alpaca-secret",
        alpaca_paper=True,
        alpaca_base_url=None,
        bridgewood_api_base="https://bridgewood.onrender.com/v1",
        bridgewood_agent_api_key="bgw_test",
        bridgewood_reporting_mode=reporting_mode,
        poll_interval_seconds=0.0 + 0.01,
        fill_timeout_seconds=0.0 + 0.05,
        http_timeout_seconds=15.0,
        report_max_attempts=max_attempts,
        report_backoff_seconds=0.0,
        log_level="INFO",
    )


def test_filled_order_is_reported_once() -> None:
    filled_order = _order(
        order_id="alpaca-order-1",
        status=BrokerOrderStatus.FILLED,
        filled_at=datetime(2026, 4, 13, 15, 45, tzinfo=UTC),
    )
    broker = FakeBroker(
        submitted_order=_order(order_id="alpaca-order-1", status=BrokerOrderStatus.NEW),
        get_order_sequence=[filled_order],
        fills={"alpaca-order-1": [_fill("alpaca-order-1")]},
    )
    reporter = FakeBridgewood(responses=[_report_response("recorded")])
    trader = Trader(broker=broker, reporter=reporter, config=_config())

    result = trader.buy("aapl", qty=Decimal("1"))

    assert result.filled is True
    assert result.report_succeeded is True
    assert result.bridgewood_execution is not None
    assert result.bridgewood_executions == [result.bridgewood_execution]
    assert result.bridgewood_execution.external_order_id == "alpaca-order-1"
    assert len(reporter.reported) == 1
    assert reporter.reported[0][0].symbol == "AAPL"


def test_broker_only_trader_can_trade_without_reporting() -> None:
    filled_order = _order(
        order_id="alpaca-order-1",
        status=BrokerOrderStatus.FILLED,
        filled_at=datetime(2026, 4, 13, 15, 45, tzinfo=UTC),
    )
    broker = FakeBroker(
        submitted_order=filled_order,
        get_order_sequence=[filled_order],
        fills={"alpaca-order-1": [_fill("alpaca-order-1")]},
    )
    trader = Trader.for_broker_only(broker=broker, config=_config())

    result = trader.buy("AAPL", qty=Decimal("1"), report_to_bridgewood=False)

    assert result.filled is True
    assert result.report_attempted is False
    assert broker.submitted_requests


def test_broker_only_trader_rejects_reporting_before_submission() -> None:
    filled_order = _order(
        order_id="alpaca-order-1",
        status=BrokerOrderStatus.FILLED,
        filled_at=datetime(2026, 4, 13, 15, 45, tzinfo=UTC),
    )
    broker = FakeBroker(
        submitted_order=filled_order,
        get_order_sequence=[filled_order],
    )
    trader = Trader.for_broker_only(broker=broker, config=_config())

    with pytest.raises(ConfigurationError, match="Bridgewood reporting was requested"):
        trader.buy("AAPL", qty=Decimal("1"))

    assert broker.submitted_requests == []


def test_duplicate_bridgewood_report_is_treated_as_success() -> None:
    filled_order = _order(
        order_id="alpaca-order-1",
        status=BrokerOrderStatus.FILLED,
        filled_at=datetime(2026, 4, 13, 15, 45, tzinfo=UTC),
    )
    broker = FakeBroker(
        submitted_order=filled_order,
        get_order_sequence=[filled_order],
        fills={"alpaca-order-1": [_fill("alpaca-order-1")]},
    )
    reporter = FakeBridgewood(responses=[_report_response("duplicate")])
    trader = Trader(broker=broker, reporter=reporter, config=_config())

    result = trader.sync_order("alpaca-order-1")

    assert result.report_succeeded is True
    assert result.bridgewood_results[0].status == "duplicate"


def test_bridgewood_failure_returns_partial_success() -> None:
    filled_order = _order(
        order_id="alpaca-order-1",
        status=BrokerOrderStatus.FILLED,
        filled_at=datetime(2026, 4, 13, 15, 45, tzinfo=UTC),
    )
    broker = FakeBroker(
        submitted_order=filled_order,
        get_order_sequence=[filled_order],
        fills={"alpaca-order-1": [_fill("alpaca-order-1")]},
    )
    reporter = FakeBridgewood(
        errors=[
            BridgewoodError("temporary outage", status_code=503),
            BridgewoodError("temporary outage", status_code=503),
        ]
    )
    trader = Trader(broker=broker, reporter=reporter, config=_config(max_attempts=2))

    result = trader.sync_order("alpaca-order-1")

    assert result.filled is True
    assert result.report_attempted is True
    assert result.report_succeeded is False
    assert result.retriable is True
    assert len(result.report_errors) == 2


def test_per_fill_reporting_mode_sends_one_execution_per_fill() -> None:
    filled_order = _order(
        order_id="alpaca-order-1",
        status=BrokerOrderStatus.FILLED,
        filled_at=datetime(2026, 4, 13, 15, 46, tzinfo=UTC),
        filled_qty=Decimal("2"),
    )
    broker = FakeBroker(
        submitted_order=filled_order,
        get_order_sequence=[filled_order],
        fills={
            "alpaca-order-1": [
                BrokerFill(
                    broker_fill_id="fill-1",
                    broker_order_id="alpaca-order-1",
                    symbol="AAPL",
                    side=OrderSide.BUY,
                    quantity=Decimal("1"),
                    price=Decimal("187.50"),
                    fees=Decimal("0.01"),
                    executed_at=datetime(2026, 4, 13, 15, 45, tzinfo=UTC),
                ),
                BrokerFill(
                    broker_fill_id="fill-2",
                    broker_order_id="alpaca-order-1",
                    symbol="AAPL",
                    side=OrderSide.BUY,
                    quantity=Decimal("1"),
                    price=Decimal("187.54"),
                    fees=Decimal("0.02"),
                    executed_at=datetime(2026, 4, 13, 15, 46, tzinfo=UTC),
                ),
            ]
        },
    )
    reporter = FakeBridgewood(
        responses=[
            BridgewoodExecutionReportResponse(
                results=[
                    BridgewoodExecutionReportResult(
                        external_order_id="alpaca-order-1:fill:fill-1",
                        status="recorded",
                        execution_id="exec-1",
                        symbol="AAPL",
                        side="buy",
                        quantity=1.0,
                        price_per_share=187.50,
                        gross_notional=187.50,
                        fees=0.01,
                        executed_at=datetime(2026, 4, 13, 15, 45, tzinfo=UTC),
                    ),
                    BridgewoodExecutionReportResult(
                        external_order_id="alpaca-order-1:fill:fill-2",
                        status="recorded",
                        execution_id="exec-2",
                        symbol="AAPL",
                        side="buy",
                        quantity=1.0,
                        price_per_share=187.54,
                        gross_notional=187.54,
                        fees=0.02,
                        executed_at=datetime(2026, 4, 13, 15, 46, tzinfo=UTC),
                    ),
                ],
                portfolio_after=_report_response("recorded").portfolio_after,
            )
        ]
    )
    trader = Trader(
        broker=broker,
        reporter=reporter,
        config=_config(reporting_mode=BridgewoodReportingMode.PER_FILL),
    )

    result = trader.sync_order("alpaca-order-1")

    assert result.bridgewood_reporting_mode == BridgewoodReportingMode.PER_FILL
    assert result.bridgewood_execution is None
    assert len(result.bridgewood_executions) == 2
    assert [item.external_order_id for item in result.bridgewood_executions] == [
        "alpaca-order-1:fill:fill-1",
        "alpaca-order-1:fill:fill-2",
    ]
    assert len(reporter.reported[0]) == 2
    assert reporter.reported[0][0].executed_at < reporter.reported[0][1].executed_at


def test_non_filled_terminal_order_is_not_reported() -> None:
    canceled_order = _order(
        order_id="alpaca-order-2",
        status=BrokerOrderStatus.CANCELED,
        filled_qty=Decimal("0"),
    )
    broker = FakeBroker(
        submitted_order=canceled_order,
        get_order_sequence=[canceled_order],
    )
    reporter = FakeBridgewood()
    trader = Trader(broker=broker, reporter=reporter, config=_config())

    result = trader.sync_order("alpaca-order-2")

    assert result.filled is False
    assert result.report_attempted is False
    assert reporter.reported == []


def test_reconcile_replays_only_filled_orders() -> None:
    older = _order(
        order_id="alpaca-order-1",
        status=BrokerOrderStatus.FILLED,
        created_at=datetime(2026, 4, 12, 15, 30, tzinfo=UTC),
        filled_at=datetime(2026, 4, 12, 15, 45, tzinfo=UTC),
    )
    newer = _order(
        order_id="alpaca-order-2",
        status=BrokerOrderStatus.FILLED,
        created_at=datetime(2026, 4, 13, 15, 30, tzinfo=UTC),
        filled_at=datetime(2026, 4, 13, 15, 45, tzinfo=UTC),
    )
    canceled = _order(
        order_id="alpaca-order-3",
        status=BrokerOrderStatus.CANCELED,
        filled_qty=Decimal("0"),
    )
    broker = FakeBroker(
        submitted_order=older,
        get_order_sequence=[older],
        fills={
            "alpaca-order-1": [_fill("alpaca-order-1", "fill-1")],
            "alpaca-order-2": [_fill("alpaca-order-2", "fill-2")],
        },
        listed_orders=[newer, canceled, older],
    )
    reporter = FakeBridgewood(
        responses=[_report_response("recorded"), _report_response("duplicate")]
    )
    trader = Trader(broker=broker, reporter=reporter, config=_config())

    result = trader.reconcile(after=timedelta(days=2), limit=10)

    assert result.checked_orders == 2
    assert result.attempted_reports == 2
    assert result.successful_reports == 2
    assert result.duplicate_reports == 1
    assert [item.broker_order_id for item in result.results] == [
        "alpaca-order-1",
        "alpaca-order-2",
    ]
