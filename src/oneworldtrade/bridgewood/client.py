from __future__ import annotations

from typing import Any

import httpx

from ..exceptions import BridgewoodError
from .models import (
    BridgewoodAgentIdentity,
    BridgewoodExecution,
    BridgewoodExecutionReportResponse,
    BridgewoodPortfolio,
)


def _normalize_base_url(base_url: str) -> str:
    stripped = base_url.strip().rstrip("/")
    if stripped.endswith("/v1"):
        return stripped
    if stripped.startswith("http://") or stripped.startswith("https://"):
        return f"{stripped}/v1"
    return stripped


def _detail_from_response(response: httpx.Response) -> str:
    try:
        payload = response.json()
    except ValueError:
        return response.text
    if isinstance(payload, dict):
        detail = payload.get("detail")
        if isinstance(detail, str):
            return detail
    return response.text


class BridgewoodClient:
    def __init__(
        self,
        *,
        base_url: str,
        agent_api_key: str,
        timeout: float = 15.0,
        client: httpx.Client | None = None,
    ) -> None:
        self.base_url = _normalize_base_url(base_url)
        self._owns_client = client is None
        self._client = client or httpx.Client(
            base_url=self.base_url,
            timeout=timeout,
            headers={
                "Authorization": f"Bearer {agent_api_key}",
                "Content-Type": "application/json",
            },
        )

    def close(self) -> None:
        if self._owns_client:
            self._client.close()

    def get_me(self) -> BridgewoodAgentIdentity:
        payload = self._request("GET", "/me")
        return BridgewoodAgentIdentity.model_validate(payload)

    def get_portfolio(self) -> BridgewoodPortfolio:
        payload = self._request("GET", "/portfolio")
        return BridgewoodPortfolio.model_validate(payload)

    def get_prices(self, symbols: list[str]) -> dict[str, Any]:
        joined = ",".join(symbol.strip().upper() for symbol in symbols if symbol.strip())
        payload = self._request("GET", "/prices", params={"symbols": joined})
        if not isinstance(payload, dict):
            raise BridgewoodError("Bridgewood /prices returned a non-object payload.")
        return payload

    def report_executions(
        self,
        executions: list[BridgewoodExecution],
    ) -> BridgewoodExecutionReportResponse:
        payload = {
            "executions": [execution.to_payload() for execution in executions],
        }
        response_payload = self._request("POST", "/executions", json=payload)
        return BridgewoodExecutionReportResponse.model_validate(response_payload)

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
            raise BridgewoodError("Timed out talking to Bridgewood.") from exc
        except httpx.HTTPError as exc:
            raise BridgewoodError("Network error while talking to Bridgewood.") from exc

        if response.is_error:
            raise BridgewoodError(
                f"Bridgewood request failed with {response.status_code}: "
                f"{_detail_from_response(response)}",
                status_code=response.status_code,
                response_text=response.text,
            )
        return response.json()
