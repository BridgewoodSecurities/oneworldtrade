from __future__ import annotations

import argparse
import json
from datetime import datetime, timedelta, timezone
from decimal import Decimal

from ..bridgewood.client import BridgewoodClient
from ..broker.alpaca import AlpacaBrokerClient
from ..config import OneWorldTradeConfig
from ..execution.trader import Trader
from ..types.orders import OrderType, TimeInForce


def _json_default(value: object) -> str:
    if isinstance(value, Decimal):
        return str(value)
    if isinstance(value, datetime):
        if value.tzinfo is None:
            return value.isoformat() + "Z"
        return value.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")
    raise TypeError(f"Object of type {type(value)!r} is not JSON serializable")


def _print(data: object) -> None:
    print(json.dumps(data, indent=2, default=_json_default))


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="oneworldtrade")
    subparsers = parser.add_subparsers(dest="command", required=True)

    config_parser = subparsers.add_parser("config", help="Inspect configuration")
    config_subparsers = config_parser.add_subparsers(
        dest="config_command", required=True
    )
    config_subparsers.add_parser("show", help="Print redacted config")

    broker_parser = subparsers.add_parser("broker", help="Broker utilities")
    broker_subparsers = broker_parser.add_subparsers(
        dest="broker_command", required=True
    )
    broker_subparsers.add_parser("verify", help="Verify Alpaca credentials")

    bridgewood_parser = subparsers.add_parser("bridgewood", help="Bridgewood utilities")
    bridgewood_subparsers = bridgewood_parser.add_subparsers(
        dest="bridgewood_command",
        required=True,
    )
    bridgewood_subparsers.add_parser("verify", help="Verify Bridgewood agent key")
    subparsers.add_parser(
        "broker-only-verify",
        help="Verify broker-only configuration without Bridgewood",
    )

    for name in ("buy", "sell"):
        command = subparsers.add_parser(name, help=f"Place a {name} order")
        command.add_argument("symbol")
        command.add_argument("--qty", required=True, type=Decimal)
        command.add_argument(
            "--order-type",
            choices=[value.value for value in OrderType],
            default=OrderType.MARKET.value,
        )
        command.add_argument("--limit-price", type=Decimal)
        command.add_argument(
            "--time-in-force",
            choices=[value.value for value in TimeInForce],
            default=TimeInForce.DAY.value,
        )
        command.add_argument("--no-wait", action="store_true")
        command.add_argument("--no-report", action="store_true")

    sync_order = subparsers.add_parser(
        "sync-order",
        help="Fetch an existing broker order and report it if fully filled",
    )
    sync_order.add_argument("broker_order_id")
    sync_order.add_argument("--no-report", action="store_true")

    reconcile = subparsers.add_parser(
        "reconcile",
        help="Replay recent filled Alpaca orders to Bridgewood",
    )
    reconcile.add_argument("--limit", type=int, default=20)
    reconcile.add_argument(
        "--after-hours",
        type=float,
        default=24.0,
        help="How far back to reconcile, in hours",
    )

    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    if args.command == "config":
        config = OneWorldTradeConfig()
        _print(config.redacted())
        return 0

    config = OneWorldTradeConfig()
    if args.command == "broker":
        config.validate_for_broker()
        broker = AlpacaBrokerClient(
            api_key=config.alpaca_api_key or "",
            secret_key=config.alpaca_secret_key or "",
            base_url=config.resolved_alpaca_base_url,
            timeout=config.http_timeout_seconds,
        )
        try:
            _print(broker.get_account().model_dump(mode="json"))
        finally:
            broker.close()
        return 0

    if args.command == "bridgewood":
        config.validate_for_bridgewood()
        reporter = BridgewoodClient(
            base_url=config.resolved_bridgewood_api_base,
            agent_api_key=config.bridgewood_agent_api_key or "",
            timeout=config.http_timeout_seconds,
        )
        try:
            _print(reporter.get_me().model_dump(mode="json"))
        finally:
            reporter.close()
        return 0

    if args.command == "broker-only-verify":
        config.validate_for_broker()
        with Trader.from_env_broker_only(config) as trader:
            _print(trader.verify_broker())
        return 0

    if args.command in {"buy", "sell"}:
        if args.no_report:
            config.validate_for_broker()
        else:
            config.validate_for_trading()
        with Trader.from_env(config) as trader:
            method = trader.buy if args.command == "buy" else trader.sell
            trade_result = method(
                args.symbol,
                qty=args.qty,
                order_type=OrderType(args.order_type),
                limit_price=args.limit_price,
                time_in_force=TimeInForce(args.time_in_force),
                wait_for_fill=not args.no_wait,
                report_to_bridgewood=not args.no_report,
            )
            _print(trade_result.model_dump(mode="json"))
            return 0

    if args.command == "sync-order":
        if args.no_report:
            config.validate_for_broker()
        else:
            config.validate_for_trading()
        with Trader.from_env(config) as trader:
            trade_result = trader.sync_order(
                args.broker_order_id,
                report_to_bridgewood=not args.no_report,
            )
            _print(trade_result.model_dump(mode="json"))
            return 0

    if args.command == "reconcile":
        config.validate_for_trading()
        with Trader.from_env(config) as trader:
            reconciliation_result = trader.reconcile(
                limit=args.limit,
                after=timedelta(hours=args.after_hours),
            )
            _print(reconciliation_result.model_dump(mode="json"))
            return 0

    return 0
