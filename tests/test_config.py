from __future__ import annotations

from oneworldtrade.config import OneWorldTradeConfig


def test_config_supports_existing_env_names(monkeypatch) -> None:
    monkeypatch.setenv("ALPACA_API_KEY", "alpaca-key")
    monkeypatch.setenv("ALPACA_SECRET_KEY", "alpaca-secret")
    monkeypatch.setenv("BRIDGEWOOD_API_BASE", "https://bridgewood.onrender.com")
    monkeypatch.setenv("BRIDGEWOOD_AGENT_API_KEY", "bgw_test_agent_key")

    config = OneWorldTradeConfig()

    assert config.alpaca_api_key == "alpaca-key"
    assert config.alpaca_secret_key == "alpaca-secret"
    assert config.resolved_bridgewood_api_base == "https://bridgewood.onrender.com/v1"
    assert config.bridgewood_agent_api_key == "bgw_test_agent_key"

