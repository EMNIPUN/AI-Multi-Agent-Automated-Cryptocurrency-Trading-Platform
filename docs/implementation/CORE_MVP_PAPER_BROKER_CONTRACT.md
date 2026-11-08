# CryptoNova — Paper Broker Contract (Prompt 65A)

| Field | Value |
| --- | --- |
| Status | Backend foundation COMPLETE (API/Studio NOT in scope) |
| Module | `agent/paper/` |
| Persistence | Local SQLite only (`data/cryptonova_paper.sqlite3` recommended) |
| Default wiring | **OFF** (`PAPER_BROKER_AUTO_ATTACH = False`) |

---

## Purpose

Local, deterministic paper simulation that turns eligible risk-approved signals into simulated orders, fills, positions, and PnL. This is **not** exchange execution and must never call Bybit private order APIs or Phase 6A adapters.

---

## Eligibility

A signal may create a paper order only when all hold:

1. Valid broker payload (`signal_id`, symbol, category, timestamps).
2. Action is `BUY` (open long) or `SELL` (close existing long only).
3. Risk verdict is `APPROVED` (not `VETO` / `BLOCKED`).
4. Action is not `HOLD` or `BLOCKED`.
5. Not a duplicate `(session_id, source_signal_id, side)`.
6. Required prices / notional present (no guessing).
7. Virtual account can fund estimated cost.
8. Portfolio guards pass (max positions, max exposure, one-per-symbol).

`execution_allowed=false` on `CoordinatorDecision` is **unchanged** and is **not** paper permission.

---

## Session / account

- Currency: USDT (virtual).
- Fields: session_id, initial/available balance, reserved capital, realized PnL, fees paid, status, config snapshot, timestamps.
- Spot-like **unleveraged longs only** in MVP.
- `SELL` closes an open long; never opens a short (`allow_short=false`).
- Position pyramiding: **unsupported** (`one_position_per_symbol=true`).

---

## Order states

`PENDING` → `FILLED` | `REJECTED` | `CANCELLED`

All orders are labeled `simulated=true`. Partial fills are **not** supported.

---

## Fill model

Historical confirmed-bar MVP:

- Entry eligible only on a confirmed candle **strictly after** `signal_candle_start_ms`.
- Fill at that candle’s **open** ± configurable adverse slippage.
- If next candle missing → order remains `PENDING` (no invented price).
- Out-of-order / duplicate candles rejected via cursor + processed-event keys.
- Invalid OHLC → rejected; no fill.

### SL / TP (longs)

| Case | Behavior |
| --- | --- |
| TP only | Exit at TP (± adverse sell slip); or gap-open if open > TP |
| SL only | Exit at SL; if open gaps below SL → executable at open ± slip |
| Both same bar | **Stop-loss first** (no LTF evidence) |
| Gap through stop | Conservative open-based fill, not guaranteed SL price |
| Duplicate exit | Idempotent; second event ignored |

OHLC limitation: intra-bar path is unknown; same-bar SL-first is a documented bias.

---

## Fees / slippage / PnL

Configurable (`fee_rate`, `slippage_bps`). Defaults are **synthetic** — not claimed Bybit tier matches.

```
entry_notional = qty × entry_fill
entry_fee = entry_notional × fee_rate
exit_notional = qty × exit_fill
exit_fee = exit_notional × fee_rate
gross = (exit_fill − entry_fill) × qty
net = gross − entry_fee − exit_fee
```

---

## Integration surface

```python
from agent.paper import PaperBroker, PaperStore, PaperBrokerConfig
from agent.paper.integration import submit_decision_to_paper  # opt-in

# Default app paths must NOT auto-call these.
```

`decision_to_paper_signal` maps `CoordinatorDecision` (`levels.stop_loss`, `risk.position_notional`, `market.newest_close_ms`, …). Missing mandatory fields → reject.

---

## Explicit non-goals (65A)

- FastAPI / Agent Studio UI
- Auto-attach to every production signal evaluation
- Futures shorts, margin, funding, liquidation, leverage
- Cloud outbox / Supabase mirror of paper rows
- Live or testnet orders
