from __future__ import annotations


class OneWorldTradeError(Exception):
    """Base exception for the package."""


class ConfigurationError(OneWorldTradeError):
    """Raised when the SDK is missing required configuration."""


class BrokerError(OneWorldTradeError):
    """Raised when broker communication or translation fails."""

    def __init__(
        self,
        message: str,
        *,
        status_code: int | None = None,
        response_text: str | None = None,
    ) -> None:
        super().__init__(message)
        self.status_code = status_code
        self.response_text = response_text

    @property
    def is_retryable(self) -> bool:
        return self.status_code is None or self.status_code in {
            408,
            409,
            429,
            500,
            502,
            503,
            504,
        }


class OrderSubmissionError(BrokerError):
    """Raised when an order cannot be submitted safely."""


class OrderFillTimeoutError(BrokerError):
    """Raised when waiting for a fill times out and strict behavior is requested."""


class BridgewoodError(OneWorldTradeError):
    """Raised when Bridgewood communication or translation fails."""

    def __init__(
        self,
        message: str,
        *,
        status_code: int | None = None,
        response_text: str | None = None,
        code: str | None = None,
        errors: list[dict[str, object]] | None = None,
    ) -> None:
        super().__init__(message)
        self.status_code = status_code
        self.response_text = response_text
        self.code = code
        self.errors = errors

    @property
    def is_retryable(self) -> bool:
        return (
            self.code == "RATE_LIMITED"
            or self.status_code is None
            or self.status_code
            in {
                408,
                429,
                500,
                502,
                503,
                504,
            }
        )


class ReconciliationError(OneWorldTradeError):
    """Raised when reconciliation cannot complete."""
