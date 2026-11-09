# CryptoNova — Autonomous PAPER Architecture

## Operator intent

CryptoNova is managed from the Orchestrator chat. The operator authorizes a bounded autonomous trading session once. The system then monitors the market, evaluates agents, applies deterministic risk vetoes, and places paper orders without typing "Approve order" for every trade.

Live Bybit trading stays disabled until separate security and operational acceptance gates pass.

## Session authorization (one start)

A single chat command such as `Start autonomous paper trading.` authorizes:

| Bound | Default |
| --- | --- |
| Mode | PAPER only |
| Symbol | HYPEUSDT USDT perpetual (linear) |
| Interval | 15m confirmed public candles |
| Capital | 5 USDT paper |
| Risk | 1% per trade (0.05 USDT risk budget) |
| Duration | 48 hours |
| Per-trade approval | false (autonomous) |
| Live / testnet orders | false |

If exchange minimums cannot fit the risk budget, the cycle returns HOLD / FLAT. The 3 USDT profit figure is a research benchmark, not an instruction to force trades.

## Control plane

Chat (and matching UI buttons) map to supervisor commands:

- `start` — authorize and run the paper session
- `pause` — stop new cycles; keep journal
- `resume` — continue the same session
- `stop` — end autonomous paper trading
- `halt` — emergency block on new entries; protective exits may still process

The OpenAI / mock Orchestrator coordinates and explains. It cannot raise leverage, set `AGENT_ALLOW_LIVE`, or call private order endpoints.

## Runtime path

```text
Orchestrator chat
  -> supervisor_command / status / analyze / report
  -> PaperSupervisor state machine
  -> PaperSupervisorWorker (background, independent of the browser)
  -> public Bybit klines
  -> SignalPipeline (market, trend, momentum, coordinator, risk)
  -> AutomaticPaperTrader (isolated SQLite journal)
```

Deterministic risk has veto authority. HOLD and BLOCKED open no position. Duplicate candles and duplicate intents are ignored. Unknown journal state or missing market data blocks new exposure.

## What stays blocked

- Live mainnet orders
- Bybit testnet order submission without separate approval
- Paid OpenAI calls without separate approval
- Development Supabase migrations from this path
- Using the Orchestrator to unlock execution mode

## Future LIVE path (not enabled)

After paper validation, testnet lifecycle tests, least-privilege database remediation, reconciliation, monitoring, and a revocable operator authorization, the same session model can target LIVE under hard capital and risk limits — still without per-trade chat approval. That cutover is a separate gate, not a chat command.
