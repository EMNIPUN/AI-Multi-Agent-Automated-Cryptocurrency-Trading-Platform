# Phase 4B — Local Database Architecture

## Path

`data/multi_agent_signals.sqlite3` (created under the API process working directory)

Separate from:

- `data/signal_ledger.sqlite3` — AgentRunner BUY/SELL dedupe
- telemetry observation SQLite — observability events
- `data/account_risk.sqlite3` — live RiskManager paper/live account risk

## Schema (v1)

### `signal_history`

Stores every coordinator decision (BUY/SELL/HOLD/BLOCKED):

- `decision_id` UNIQUE, `idempotent_key` UNIQUE
- symbol / category / interval / timestamps
- `strategy_version`, `config_hash`
- action, signal_strength, directional_conviction, market_quality
- risk_verdict, source_mode (`LIVE_PUBLIC` | `REPLAY` | `SIMULATED`)
- JSON columns: reason_codes, contributions, risk, levels, market, indicators

Indexes on timestamp, symbol+interval, action, strategy_version.

### `paper_risk_state` (singleton id=1)

Durable recovery for:

- `halted` (daily hypothetical loss)
- `hypothetical_day_pnl`, `day_key`
- cooldown fields (`last_signal_key`, `last_signal_ms`)
- `seen_keys_json` (bounded)
- `corrupt` flag — fail closed; **never auto-clears a halt on API restart**

### `schema_meta`

`schema_version` for migration safety.

## Concurrency

- WAL mode
- `BEGIN IMMEDIATE` on inserts / risk updates
- Thread RLock around store operations
- Idempotent inserts via UNIQUE constraints

## Secrets

Sanitize via `sanitize_public_json` before insert. No API keys, tokens, or wallet secrets.
