from __future__ import annotations

from pydantic import AliasChoices, Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

from .exceptions import ConfigurationError
from .types.reporting import BridgewoodReportingMode


def _strip_trailing_slash(value: str) -> str:
    stripped = value.strip()
    if not stripped:
        return stripped
    return stripped.rstrip("/")


class OneWorldTradeConfig(BaseSettings):
    model_config = SettingsConfigDict(
        extra="ignore",
    )

    alpaca_api_key: str | None = Field(
        default=None,
        validation_alias=AliasChoices(
            "ALPACA_API_KEY",
            "APCA_API_KEY_ID",
            "ONEWORLDTRADE_ALPACA_API_KEY",
        ),
    )
    alpaca_secret_key: str | None = Field(
        default=None,
        validation_alias=AliasChoices(
            "ALPACA_SECRET_KEY",
            "APCA_API_SECRET_KEY",
            "ONEWORLDTRADE_ALPACA_SECRET_KEY",
        ),
    )
    alpaca_paper: bool = Field(
        default=True,
        validation_alias=AliasChoices(
            "ONEWORLDTRADE_ALPACA_PAPER",
            "ALPACA_PAPER",
        ),
    )
    alpaca_base_url: str | None = Field(
        default=None,
        validation_alias=AliasChoices(
            "ONEWORLDTRADE_ALPACA_BASE_URL",
            "ALPACA_BASE_URL",
        ),
    )
    bridgewood_api_base: str = Field(
        default="https://bridgewood.onrender.com/v1",
        validation_alias=AliasChoices(
            "BRIDGEWOOD_API_BASE",
            "ONEWORLDTRADE_BRIDGEWOOD_API_BASE",
        ),
    )
    bridgewood_agent_api_key: str | None = Field(
        default=None,
        validation_alias=AliasChoices(
            "BRIDGEWOOD_AGENT_API_KEY",
            "ONEWORLDTRADE_BRIDGEWOOD_AGENT_API_KEY",
        ),
    )
    bridgewood_reporting_mode: BridgewoodReportingMode = Field(
        default=BridgewoodReportingMode.AGGREGATED_ORDER,
        validation_alias=AliasChoices(
            "ONEWORLDTRADE_BRIDGEWOOD_REPORTING_MODE",
        ),
    )
    poll_interval_seconds: float = Field(
        default=2.0,
        validation_alias=AliasChoices(
            "ONEWORLDTRADE_POLL_INTERVAL_SECONDS",
        ),
    )
    fill_timeout_seconds: float = Field(
        default=120.0,
        validation_alias=AliasChoices(
            "ONEWORLDTRADE_FILL_TIMEOUT_SECONDS",
        ),
    )
    http_timeout_seconds: float = Field(
        default=15.0,
        validation_alias=AliasChoices(
            "ONEWORLDTRADE_HTTP_TIMEOUT_SECONDS",
        ),
    )
    report_max_attempts: int = Field(
        default=3,
        validation_alias=AliasChoices(
            "ONEWORLDTRADE_REPORT_MAX_ATTEMPTS",
        ),
    )
    report_backoff_seconds: float = Field(
        default=1.0,
        validation_alias=AliasChoices(
            "ONEWORLDTRADE_REPORT_BACKOFF_SECONDS",
        ),
    )
    log_level: str = Field(
        default="INFO",
        validation_alias=AliasChoices(
            "ONEWORLDTRADE_LOG_LEVEL",
        ),
    )

    @field_validator("alpaca_api_key", "alpaca_secret_key", "bridgewood_agent_api_key")
    @classmethod
    def _normalize_optional_secret(cls, value: str | None) -> str | None:
        if value is None:
            return None
        stripped = value.strip()
        return stripped or None

    @field_validator("alpaca_base_url", "bridgewood_api_base")
    @classmethod
    def _normalize_url(cls, value: str | None) -> str | None:
        if value is None:
            return None
        stripped = _strip_trailing_slash(value)
        return stripped or None

    @field_validator(
        "poll_interval_seconds", "fill_timeout_seconds", "http_timeout_seconds"
    )
    @classmethod
    def _validate_positive_float(cls, value: float) -> float:
        if value <= 0:
            raise ValueError("timeouts and polling intervals must be positive")
        return value

    @field_validator("report_max_attempts")
    @classmethod
    def _validate_attempts(cls, value: int) -> int:
        if value < 1:
            raise ValueError("report_max_attempts must be at least 1")
        return value

    @property
    def resolved_alpaca_base_url(self) -> str:
        if self.alpaca_base_url:
            return self.alpaca_base_url
        if self.alpaca_paper:
            return "https://paper-api.alpaca.markets"
        return "https://api.alpaca.markets"

    @property
    def resolved_bridgewood_api_base(self) -> str:
        base = self.bridgewood_api_base
        if not base:
            raise ConfigurationError("BRIDGEWOOD_API_BASE is not configured.")
        if base.endswith("/v1"):
            return base
        return f"{base}/v1"

    def validate_for_trading(self) -> None:
        missing: list[str] = []
        if not self.alpaca_api_key:
            missing.append("ALPACA_API_KEY")
        if not self.alpaca_secret_key:
            missing.append("ALPACA_SECRET_KEY")
        if not self.bridgewood_agent_api_key:
            missing.append("BRIDGEWOOD_AGENT_API_KEY")
        if missing:
            raise ConfigurationError(
                "Missing required configuration: " + ", ".join(missing)
            )

    def validate_for_broker(self) -> None:
        missing: list[str] = []
        if not self.alpaca_api_key:
            missing.append("ALPACA_API_KEY")
        if not self.alpaca_secret_key:
            missing.append("ALPACA_SECRET_KEY")
        if missing:
            raise ConfigurationError(
                "Missing required broker configuration: " + ", ".join(missing)
            )

    def validate_for_bridgewood(self) -> None:
        if not self.bridgewood_agent_api_key:
            raise ConfigurationError(
                "Missing required Bridgewood configuration: BRIDGEWOOD_AGENT_API_KEY"
            )

    def redacted(self) -> dict[str, object]:
        def _redact(value: str | None) -> str | None:
            if value is None:
                return None
            if len(value) <= 8:
                return "*" * len(value)
            return f"{value[:4]}...{value[-4:]}"

        return {
            "alpaca_api_key": _redact(self.alpaca_api_key),
            "alpaca_secret_key": _redact(self.alpaca_secret_key),
            "alpaca_paper": self.alpaca_paper,
            "alpaca_base_url": self.resolved_alpaca_base_url,
            "bridgewood_api_base": self.resolved_bridgewood_api_base,
            "bridgewood_agent_api_key": _redact(self.bridgewood_agent_api_key),
            "bridgewood_reporting_mode": self.bridgewood_reporting_mode.value,
            "poll_interval_seconds": self.poll_interval_seconds,
            "fill_timeout_seconds": self.fill_timeout_seconds,
            "http_timeout_seconds": self.http_timeout_seconds,
            "report_max_attempts": self.report_max_attempts,
            "report_backoff_seconds": self.report_backoff_seconds,
            "log_level": self.log_level,
        }
