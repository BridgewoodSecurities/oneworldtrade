from __future__ import annotations

from datetime import datetime, timezone

import httpx
import pytest

from oneworldtrade.bridgewood.client import BridgewoodClient
from oneworldtrade.exceptions import BridgewoodError


UTC = timezone.utc


def test_list_executions_returns_execution_page() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.method == "GET"
        assert request.url.path == "/v1/executions"
        assert request.url.params["limit"] == "2"
        assert request.url.params["cursor"] == "cursor-1"
        return httpx.Response(
            200,
            json={
                "items": [
                    {
                        "id": "exec-1",
                        "external_order_id": "alpaca-order-1",
                        "symbol": "AAPL",
                        "side": "buy",
                        "quantity": 1.0,
                        "price_per_share": 187.52,
                        "gross_notional": 187.52,
                        "fees": 0.0,
                        "realized_pnl": 0.0,
                        "executed_at": datetime(
                            2026, 4, 13, 15, 45, tzinfo=UTC
                        ).isoformat(),
                        "created_at": datetime(
                            2026, 4, 13, 15, 45, tzinfo=UTC
                        ).isoformat(),
                    }
                ],
                "next_cursor": "cursor-2",
            },
        )

    client = BridgewoodClient(
        base_url="https://bridgewood.onrender.com/v1",
        agent_api_key="bgw_test",
        client=httpx.Client(
            base_url="https://bridgewood.onrender.com/v1",
            transport=httpx.MockTransport(handler),
            headers={"Authorization": "Bearer bgw_test"},
        ),
    )

    page = client.list_executions(limit=2, cursor="cursor-1")

    assert page.next_cursor == "cursor-2"
    assert page.items[0].external_order_id == "alpaca-order-1"


def test_structured_bridgewood_error_is_parsed() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        del request
        return httpx.Response(
            400,
            json={
                "detail": "Insufficient quantity to sell 1 AAPL.",
                "code": "INSUFFICIENT_POSITION",
                "errors": [{"loc": ["body", "executions", 0]}],
            },
        )

    client = BridgewoodClient(
        base_url="https://bridgewood.onrender.com/v1",
        agent_api_key="bgw_test",
        client=httpx.Client(
            base_url="https://bridgewood.onrender.com/v1",
            transport=httpx.MockTransport(handler),
            headers={"Authorization": "Bearer bgw_test"},
        ),
    )

    with pytest.raises(BridgewoodError) as exc_info:
        client.get_portfolio()

    error = exc_info.value
    assert error.status_code == 400
    assert error.code == "INSUFFICIENT_POSITION"
    assert error.errors == [{"loc": ["body", "executions", 0]}]
    assert "INSUFFICIENT_POSITION" in str(error)
