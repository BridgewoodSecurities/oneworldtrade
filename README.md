# oneworldtrade

`oneworldtrade` is the agent-side trading SDK that executes orders through a broker and reliably reports resulting fills to Bridgewood.

## What It Does

`oneworldtrade` sits between your strategy code and the external systems:

```text
agent -> oneworldtrade -> Alpaca + Bridgewood
```

The agent decides *what* to trade.

`oneworldtrade` handles:

- speaking Alpaca correctly
- waiting for a final fill outcome
- normalizing the resulting execution
- reporting the completed fill to Bridgewood
- retrying Bridgewood reporting safely
- returning a structured result object instead of a vague success boolean

## What It Does Not Do

This package is intentionally narrow.

It is not:

- a strategy framework
- a scheduler
- a bot runner
- a portfolio analytics suite
- a replacement for Bridgewood
- a replacement for Alpaca

In v1 it only supports:

- Alpaca equities
- Bridgewood agent-side reporting
- fully filled orders only
- synchronous workflows

Bridgewood is treated as an external dependency. `oneworldtrade` does not provision Bridgewood accounts or agents and only uses an existing `BRIDGEWOOD_AGENT_API_KEY`.

If you want broker-only usage, `oneworldtrade` supports that too. A `Trader`
can be constructed without Bridgewood credentials and used with
`report_to_bridgewood=False`.

## Install

```bash
pip install oneworldtrade
```

For local development:

```bash
python -m venv .venv
./.venv/bin/pip install -e ".[dev]"
```

## Environment

`Trader.from_env()` reads from the ambient process environment provided by the
agent runtime, shell, container, or deployment platform. `oneworldtrade` does
not auto-load a local `.env` file.

Minimum environment:

```bash
ALPACA_API_KEY=...
ALPACA_SECRET_KEY=...
BRIDGEWOOD_AGENT_API_KEY=bgw_...
```

Optional:

```bash
ONEWORLDTRADE_ALPACA_PAPER=true
BRIDGEWOOD_API_BASE=https://bridgewood.onrender.com/v1
ONEWORLDTRADE_BRIDGEWOOD_REPORTING_MODE=aggregated_order
ONEWORLDTRADE_POLL_INTERVAL_SECONDS=2
ONEWORLDTRADE_FILL_TIMEOUT_SECONDS=120
ONEWORLDTRADE_HTTP_TIMEOUT_SECONDS=15
ONEWORLDTRADE_REPORT_MAX_ATTEMPTS=3
ONEWORLDTRADE_REPORT_BACKOFF_SECONDS=1
ONEWORLDTRADE_LOG_LEVEL=INFO
```

If you want `.env` loading in your own agent repo, do that at the application
layer before constructing `Trader`.

## Broker-only Usage

```python
from oneworldtrade import Trader

trader = Trader.from_env_broker_only()
result = trader.buy("AAPL", qty=1, report_to_bridgewood=False)
```

If Bridgewood reporting is requested without a configured reporter,
`oneworldtrade` raises a configuration error before the order is submitted.

## Quick Start

```python
from oneworldtrade import Trader

trader = Trader.from_env()

result = trader.buy("AAPL", qty=1)

if result.report_succeeded:
    print("Filled and reported to Bridgewood")
elif result.filled:
    print("Filled at broker, but Bridgewood reporting needs attention")
else:
    print(f"Order status: {result.broker_status}")
```

## Advanced Usage

```python
from decimal import Decimal

from oneworldtrade import OrderType, TimeInForce, Trader

trader = Trader.from_env()

result = trader.place_order(
    symbol="AAPL",
    side="buy",
    qty=Decimal("2"),
    order_type=OrderType.LIMIT,
    limit_price=Decimal("180"),
    time_in_force=TimeInForce.DAY,
)
```

## Reconciliation

`oneworldtrade` is designed to recover cleanly from the important partial-failure case:

1. Alpaca fills the order.
2. Bridgewood reporting fails temporarily.
3. The agent replays the filled order later.

Because Bridgewood deduplicates on `external_order_id`, `oneworldtrade`
defaults to using the stable Alpaca order ID when reporting a fully filled
order. Replays are safe.

The default reporting mode is `aggregated_order`, which reports one
Bridgewood execution per filled Alpaca order. For future flexibility, the
package also supports a `per_fill` reporting mode that emits one Bridgewood
execution per broker fill after the order reaches a final filled state.

```python
reconciliation = trader.reconcile(limit=20)
print(reconciliation.successful_reports)
```

## CLI

The package includes a small CLI:

```bash
oneworldtrade config show
oneworldtrade broker verify
oneworldtrade bridgewood verify
oneworldtrade broker-only-verify
oneworldtrade buy AAPL --qty 1
oneworldtrade sell TSLA --qty 1
oneworldtrade sync-order <broker-order-id>
oneworldtrade reconcile --limit 20
```

## Design Notes

- Only fully filled orders are reported to Bridgewood.
- Bridgewood setup is human-owned and outside the package scope.
- Alpaca is wrapped behind a broker client interface so future brokers can be added without rewriting strategy code.
- The default public API is `Trader`.
- Naive execution timestamps are rejected rather than silently assumed to be UTC.
- Lower-level broker and Bridgewood clients are still available when needed.
