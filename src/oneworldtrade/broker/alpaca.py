from __future__ import annotations

import time
from collections.abc import Sequence
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal
from typing import Any

import httpx

from ..exceptions import BrokerError, OrderSubmissionError
from ..log import get_logger
from ..types.fills import BrokerFill
from ..types.orders import OrderRequest, OrderSide, OrderType, TimeInForce
from .base import BrokerClient
from .models import (
    BrokerAccountIdentity,
    BrokerOrder,
    BrokerOrderStatus,
)


LOGGER = get_logger(__name__)


def _parse_datetime(value: str | None) -> datetime | None:
    if value is None or value == "":
        return None
    normalized = value.replace("Z", "+00:00")
    parsed = datetime.fromisoformat(normalized)
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def _detail_from_response(response: httpx.Response) -> str:
    try:
        payload = response.json()
    except ValueError:
        return response.text
    if isinstance(payload, dict):
        detail = payload.get("detail") or payload.get("message")
        if isinstance(detail, str):
            return detail
    return response.text


class AlpacaBrokerClient(BrokerClient):
    _SUBMISSION_RECOVERY_ATTEMPTS = 3
    _SUBMISSION_RECOVERY_DELAY_SECONDS = 1.0

    def __init__(
        self,
        *,
        api_key: str,
        secret_key: str,
        base_url: str,
        timeout: float = 15.0,
        client: httpx.Client | None = None,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self._owns_client = client is None
        self._client = client or httpx.Client(
            base_url=self.base_url,
            timeout=timeout,
            headers={
                "APCA-API-KEY-ID": api_key,
                "APCA-API-SECRET-KEY": secret_key,
                "Content-Type": "application/json",
            },
        )

    def close(self) -> None:
        if self._owns_client:
            self._client.close()

    def get_account(self) -> BrokerAccountIdentity:
        payload = self._request("GET", "/v2/account")
        return BrokerAccountIdentity(
            account_id=str(payload["id"]),
            account_number=payload.get("account_number"),
            status=payload.get("status"),
            currency=payload.get("currency"),
            buying_power=payload.get("buying_power"),
            raw=payload,
        )

    def submit_order(self, request: OrderRequest) -> BrokerOrder:
        payload: dict[str, Any] = {
            "symbol": request.symbol,
            "qty": str(request.qty),
            "side": request.side.value,
            "type": request.order_type.value,
            "time_in_force": request.time_in_force.value,
            "extended_hours": request.extended_hours,
        }
        if request.client_order_id:
            payload["client_order_id"] = request.client_order_id
        if request.order_type == OrderType.LIMIT and request.limit_price is not None:
            payload["limit_price"] = str(request.limit_price)

        try:
            response_payload = self._request("POST", "/v2/orders", json=payload)
        except BrokerError as exc:
            if request.client_order_id and exc.is_retryable:
                recovered = self._recover_submitted_order(request.client_order_id)
                if recovered is not None:
                    return recovered
            raise OrderSubmissionError(
                f"Unable to submit order to Alpaca: {exc}",
                status_code=exc.status_code,
                response_text=exc.response_text,
            ) from exc

        return self._parse_order(response_payload)

    def get_order(self, broker_order_id: str) -> BrokerOrder:
        payload = self._request("GET", f"/v2/orders/{broker_order_id}")
        return self._parse_order(payload)

    def get_order_by_client_order_id(self, client_order_id: str) -> BrokerOrder:
        payload = self._request(
            "GET",
            "/v2/orders:by_client_order_id",
            params={"client_order_id": client_order_id},
        )
        return self._parse_order(payload)

    def list_orders(
        self,
        *,
        status: str = "all",
        after: datetime | None = None,
        limit: int = 50,
    ) -> Sequence[BrokerOrder]:
        params: dict[str, str | int] = {"status": status, "limit": limit}
        if after is not None:
            params["after"] = after.astimezone(timezone.utc).isoformat()
        payload = self._request("GET", "/v2/orders", params=params)
        return [self._parse_order(item) for item in payload]

    def list_fills(self, broker_order_id: str) -> Sequence[BrokerFill]:
        order = self.get_order(broker_order_id)
        if order.created_at is None and order.filled_at is None:
            payload = self._request(
                "GET",
                "/v2/account/activities/FILL",
                params={"page_size": 100, "direction": "desc"},
            )
            return self._parse_fill_activities(payload, broker_order_id)

        dates = self._dates_to_query(order)
        collected: dict[str, BrokerFill] = {}
        for single_date in dates:
            payload = self._request(
                "GET",
                "/v2/account/activities/FILL",
                params={"date": single_date.isoformat()},
            )
            for fill in self._parse_fill_activities(payload, broker_order_id):
                collected[fill.broker_fill_id] = fill
        return sorted(collected.values(), key=lambda fill: fill.executed_at)

    def _dates_to_query(self, order: BrokerOrder) -> list[date]:
        start = (
            order.created_at or order.filled_at or datetime.now(timezone.utc)
        ).date()
        end = (order.filled_at or order.created_at or datetime.now(timezone.utc)).date()
        if end < start:
            start, end = end, start
        dates: list[date] = []
        current = start
        for _ in range(10):
            dates.append(current)
            if current >= end:
                break
            current += timedelta(days=1)
        return dates

    def _parse_fill_activities(
        self,
        payload: Any,
        broker_order_id: str,
    ) -> list[BrokerFill]:
        if not isinstance(payload, list):
            return []
        fills: list[BrokerFill] = []
        for item in payload:
            if not isinstance(item, dict):
                continue
            if item.get("order_id") != broker_order_id:
                continue
            fills.append(
                BrokerFill(
                    broker_fill_id=str(item["id"]),
                    broker_order_id=str(item["order_id"]),
                    symbol=str(item["symbol"]),
                    side=OrderSide(str(item["side"])),
                    quantity=Decimal(str(item["qty"])),
                    price=Decimal(str(item["price"])),
                    fees=Decimal("0"),
                    executed_at=_parse_datetime(item["transaction_time"])
                    or datetime.now(timezone.utc),
                    raw=item,
                )
            )
        return fills

    def _recover_submitted_order(self, client_order_id: str) -> BrokerOrder | None:
        for attempt in range(self._SUBMISSION_RECOVERY_ATTEMPTS):
            try:
                return self.get_order_by_client_order_id(client_order_id)
            except BrokerError as exc:
                LOGGER.warning(
                    "Unable to recover submitted Alpaca order by client_order_id=%s: %s",
                    client_order_id,
                    exc,
                )
                if attempt + 1 == self._SUBMISSION_RECOVERY_ATTEMPTS:
                    break
                time.sleep(self._SUBMISSION_RECOVERY_DELAY_SECONDS)
        return None

    def _request(
        self,
        method: str,
        path: str,
        *,
        params: dict[str, Any] | None = None,
        json: dict[str, Any] | None = None,
    ) -> Any:
        try:
            response = self._client.request(method, path, params=params, json=json)
        except httpx.TimeoutException as exc:
            raise BrokerError("Timed out talking to Alpaca.") from exc
        except httpx.HTTPError as exc:
            raise BrokerError("Network error while talking to Alpaca.") from exc

        if response.is_error:
            raise BrokerError(
                f"Alpaca request failed with {response.status_code}: "
                f"{_detail_from_response(response)}",
                status_code=response.status_code,
                response_text=response.text,
            )
        return response.json()

    def _parse_order(self, payload: dict[str, Any]) -> BrokerOrder:
        return BrokerOrder(
            broker_name="alpaca",
            order_id=str(payload["id"]),
            client_order_id=payload.get("client_order_id"),
            symbol=str(payload["symbol"]),
            side=OrderSide(str(payload["side"])),
            order_type=OrderType(str(payload.get("type") or payload.get("order_type"))),
            time_in_force=TimeInForce(str(payload["time_in_force"])),
            status=BrokerOrderStatus(str(payload["status"])),
            qty=Decimal(str(payload.get("qty") or "0")),
            filled_qty=Decimal(str(payload.get("filled_qty") or "0")),
            filled_avg_price=(
                Decimal(str(payload["filled_avg_price"]))
                if payload.get("filled_avg_price") is not None
                else None
            ),
            limit_price=(
                Decimal(str(payload["limit_price"]))
                if payload.get("limit_price") is not None
                else None
            ),
            extended_hours=bool(payload.get("extended_hours", False)),
            created_at=_parse_datetime(payload.get("created_at")),
            submitted_at=_parse_datetime(payload.get("submitted_at")),
            filled_at=_parse_datetime(payload.get("filled_at")),
            canceled_at=_parse_datetime(payload.get("canceled_at")),
            expired_at=_parse_datetime(payload.get("expired_at")),
            failed_at=_parse_datetime(payload.get("failed_at")),
            raw=payload,
        )
