from __future__ import annotations

import time
from types import TracebackType
from datetime import datetime, timedelta, timezone
from decimal import Decimal

from ..bridgewood.models import BridgewoodExecution
from ..bridgewood.client import BridgewoodClient
from ..bridgewood.models import BridgewoodExecutionReportResponse
from ..broker.alpaca import AlpacaBrokerClient
from ..broker.base import BrokerClient
from ..config import OneWorldTradeConfig
from ..exceptions import BridgewoodError
from ..logging import configure_logging, get_logger
from ..types.fills import BrokerFill
from ..types.orders import OrderRequest, OrderSide, OrderType, TimeInForce
from ..types.results import ReconciliationResult, TradeResult
from .idempotency import bridgewood_execution_from_order, build_client_order_id
from .lifecycle import wait_for_terminal_order
from .reconciliation import resolve_after_timestamp, summarize_reconciliation


LOGGER = get_logger(__name__)


class Trader:
    def __init__(
        self,
        *,
        broker: BrokerClient,
        reporter: BridgewoodClient,
        config: OneWorldTradeConfig,
    ) -> None:
        self.broker = broker
        self.reporter = reporter
        self.config = config

    @classmethod
    def from_env(cls, config: OneWorldTradeConfig | None = None) -> "Trader":
        resolved_config = config or OneWorldTradeConfig()
        resolved_config.validate_for_trading()
        configure_logging(resolved_config.log_level)

        broker = AlpacaBrokerClient(
            api_key=resolved_config.alpaca_api_key or "",
            secret_key=resolved_config.alpaca_secret_key or "",
            base_url=resolved_config.resolved_alpaca_base_url,
            timeout=resolved_config.http_timeout_seconds,
        )
        reporter = BridgewoodClient(
            base_url=resolved_config.resolved_bridgewood_api_base,
            agent_api_key=resolved_config.bridgewood_agent_api_key or "",
            timeout=resolved_config.http_timeout_seconds,
        )
        return cls(broker=broker, reporter=reporter, config=resolved_config)

    def close(self) -> None:
        self.broker.close()
        self.reporter.close()

    def __enter__(self) -> "Trader":
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        tb: TracebackType | None,
    ) -> None:
        del exc_type, exc, tb
        self.close()

    def verify_broker(self) -> dict[str, object]:
        account = self.broker.get_account()
        return account.model_dump(mode="json")

    def verify_bridgewood(self) -> dict[str, object]:
        identity = self.reporter.get_me()
        return identity.model_dump(mode="json")

    def buy(
        self,
        symbol: str,
        *,
        qty: Decimal | int | float | str,
        order_type: OrderType = OrderType.MARKET,
        limit_price: Decimal | int | float | str | None = None,
        time_in_force: TimeInForce = TimeInForce.DAY,
        wait_for_fill: bool = True,
        report_to_bridgewood: bool = True,
        client_order_id: str | None = None,
    ) -> TradeResult:
        return self.place_order(
            symbol=symbol,
            side=OrderSide.BUY,
            qty=qty,
            order_type=order_type,
            limit_price=limit_price,
            time_in_force=time_in_force,
            wait_for_fill=wait_for_fill,
            report_to_bridgewood=report_to_bridgewood,
            client_order_id=client_order_id,
        )

    def sell(
        self,
        symbol: str,
        *,
        qty: Decimal | int | float | str,
        order_type: OrderType = OrderType.MARKET,
        limit_price: Decimal | int | float | str | None = None,
        time_in_force: TimeInForce = TimeInForce.DAY,
        wait_for_fill: bool = True,
        report_to_bridgewood: bool = True,
        client_order_id: str | None = None,
    ) -> TradeResult:
        return self.place_order(
            symbol=symbol,
            side=OrderSide.SELL,
            qty=qty,
            order_type=order_type,
            limit_price=limit_price,
            time_in_force=time_in_force,
            wait_for_fill=wait_for_fill,
            report_to_bridgewood=report_to_bridgewood,
            client_order_id=client_order_id,
        )

    def place_order(
        self,
        *,
        symbol: str,
        side: OrderSide | str,
        qty: Decimal | int | float | str,
        order_type: OrderType | str = OrderType.MARKET,
        limit_price: Decimal | int | float | str | None = None,
        time_in_force: TimeInForce | str = TimeInForce.DAY,
        wait_for_fill: bool = True,
        report_to_bridgewood: bool = True,
        client_order_id: str | None = None,
        raise_on_report_failure: bool = False,
    ) -> TradeResult:
        normalized_side = OrderSide(side)
        normalized_qty = Decimal(str(qty))
        normalized_order_type = OrderType(order_type)
        normalized_limit_price = (
            Decimal(str(limit_price)) if limit_price is not None else None
        )
        normalized_time_in_force = TimeInForce(time_in_force)
        request = OrderRequest(
            symbol=symbol,
            side=normalized_side,
            qty=normalized_qty,
            order_type=normalized_order_type,
            limit_price=normalized_limit_price,
            time_in_force=normalized_time_in_force,
            client_order_id=client_order_id or build_client_order_id(),
        )
        submitted_order = self.broker.submit_order(request)
        LOGGER.info(
            "Submitted Alpaca order %s for %s %s %s",
            submitted_order.order_id,
            request.side.value,
            request.qty,
            request.symbol,
        )

        result = TradeResult(
            order_request=request,
            broker_order_id=submitted_order.order_id,
            broker_order=submitted_order,
            wait_for_fill=wait_for_fill,
            report_requested=report_to_bridgewood,
        )

        if not wait_for_fill:
            return result

        lifecycle = wait_for_terminal_order(
            self.broker,
            submitted_order.order_id,
            poll_interval_seconds=self.config.poll_interval_seconds,
            timeout_seconds=self.config.fill_timeout_seconds,
        )
        result.broker_order = lifecycle.order
        result.timed_out = lifecycle.timed_out

        if lifecycle.timed_out:
            LOGGER.info(
                "Order %s did not reach a terminal state before timeout.",
                submitted_order.order_id,
            )
            result.retriable = True
            return result

        return self._sync_result(
            result,
            report_to_bridgewood=report_to_bridgewood,
            raise_on_report_failure=raise_on_report_failure,
        )

    def sync_order(
        self,
        broker_order_id: str,
        *,
        report_to_bridgewood: bool = True,
        raise_on_report_failure: bool = False,
    ) -> TradeResult:
        order = self.broker.get_order(broker_order_id)
        request = OrderRequest(
            symbol=order.symbol,
            side=order.side,
            qty=order.qty,
            order_type=order.order_type,
            limit_price=order.limit_price,
            time_in_force=order.time_in_force,
            client_order_id=order.client_order_id,
        )
        result = TradeResult(
            order_request=request,
            broker_order_id=order.order_id,
            broker_order=order,
            wait_for_fill=False,
            report_requested=report_to_bridgewood,
        )
        return self._sync_result(
            result,
            report_to_bridgewood=report_to_bridgewood,
            raise_on_report_failure=raise_on_report_failure,
        )

    def reconcile(
        self,
        *,
        after: datetime | timedelta | None = timedelta(days=1),
        limit: int = 50,
        raise_on_report_failure: bool = False,
    ) -> ReconciliationResult:
        after_timestamp = resolve_after_timestamp(after)
        orders = list(
            self.broker.list_orders(status="closed", after=after_timestamp, limit=limit)
        )
        ordered_fills = sorted(
            [order for order in orders if order.is_filled],
            key=lambda order: (
                order.filled_at or order.created_at or datetime.now(timezone.utc)
            ),
        )
        results = [
            self.sync_order(
                order.order_id,
                report_to_bridgewood=True,
                raise_on_report_failure=raise_on_report_failure,
            )
            for order in ordered_fills
        ]
        return summarize_reconciliation(results)

    def _sync_result(
        self,
        result: TradeResult,
        *,
        report_to_bridgewood: bool,
        raise_on_report_failure: bool,
    ) -> TradeResult:
        if result.broker_order is None:
            return result

        fills = self._load_fills(result.broker_order.order_id)
        result.fills = fills

        if not result.broker_order.is_filled:
            LOGGER.info(
                "Order %s finished with status %s and will not be reported to Bridgewood.",
                result.broker_order.order_id,
                result.broker_order.status.value,
            )
            return result

        if not report_to_bridgewood:
            return result

        execution = bridgewood_execution_from_order(result.broker_order, fills)
        result.bridgewood_execution = execution

        response = self._report_execution(
            execution,
            raise_on_report_failure=raise_on_report_failure,
            result=result,
        )
        if response is not None:
            result.bridgewood_results = response.results
            result.report_succeeded = all(
                item.status in {"recorded", "duplicate"} for item in response.results
            )
            result.retriable = not result.report_succeeded
        return result

    def _load_fills(self, broker_order_id: str) -> list[BrokerFill]:
        try:
            return list(self.broker.list_fills(broker_order_id))
        except Exception as exc:
            LOGGER.warning(
                "Unable to fetch fills for Alpaca order %s: %s",
                broker_order_id,
                exc,
            )
            return []

    def _report_execution(
        self,
        execution: BridgewoodExecution,
        *,
        raise_on_report_failure: bool,
        result: TradeResult,
    ) -> BridgewoodExecutionReportResponse | None:
        last_error: BridgewoodError | None = None
        result.report_attempted = True

        for attempt in range(1, self.config.report_max_attempts + 1):
            try:
                response = self.reporter.report_executions([execution])
            except BridgewoodError as exc:
                last_error = exc
                result.report_errors.append(str(exc))
                LOGGER.warning(
                    "Bridgewood report attempt %s failed for order %s: %s",
                    attempt,
                    execution.external_order_id,
                    exc,
                )
                if attempt >= self.config.report_max_attempts or not exc.is_retryable:
                    result.report_succeeded = False
                    result.retriable = exc.is_retryable
                    if raise_on_report_failure:
                        raise
                    return None
                time.sleep(self.config.report_backoff_seconds * attempt)
                continue

            LOGGER.info(
                "Reported filled order %s to Bridgewood.",
                execution.external_order_id,
            )
            result.report_succeeded = True
            result.retriable = False
            return response

        if raise_on_report_failure and last_error is not None:
            raise last_error
        return None
