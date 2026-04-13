from __future__ import annotations

from typing import Any

import httpx

from ..exceptions import BridgewoodError
from .models import (
    BridgewoodAgentIdentity,
    BridgewoodErrorPayload,
    BridgewoodExecution,
    BridgewoodExecutionPage,
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


def _error_from_response(
    response: httpx.Response,
) -> tuple[str, str | None, list[dict[str, object]] | None]:
    try:
        payload = response.json()
    except ValueError:
        return response.text, None, None
    if isinstance(payload, dict):
        try:
            parsed = BridgewoodErrorPayload.model_validate(payload)
        except Exception:
            detail = payload.get("detail")
            if isinstance(detail, str):
                return detail, None, None
        else:
            return parsed.detail, parsed.code, parsed.errors
    return response.text, None, None


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

    def list_executions(
        self,
        *,
        limit: int = 100,
        cursor: str | None = None,
    ) -> BridgewoodExecutionPage:
        payload = self._request(
            "GET",
            "/executions",
            params={
                "limit": limit,
                **({"cursor": cursor} if cursor else {}),
            },
        )
        return BridgewoodExecutionPage.model_validate(payload)

    def get_prices(self, symbols: list[str]) -> dict[str, Any]:
        joined = ",".join(
            symbol.strip().upper() for symbol in symbols if symbol.strip()
        )
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
            detail, code, errors = _error_from_response(response)
            code_fragment = f" {code}:" if code else ":"
            raise BridgewoodError(
                f"Bridgewood request failed with {response.status_code}"
                f"{code_fragment} {detail}",
                status_code=response.status_code,
                response_text=response.text,
                code=code,
                errors=errors,
            )
        return response.json()
