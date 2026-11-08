# Phase 4D — Database Schema Plan

## Existing (reuse — do not duplicate)

| Table | Role |
|-------|------|
| `app.agent_decisions` | Observational decision log (different shape; not multi-agent SoT) |
| `app.system_events` | Ops events |
| `app.strategy_configs` | Named strategy configuration documents |
| `app.exchange_account_bindings` | Owner-bound exchange refs (persistence still OFF) |

## Implement now (proposed migration `20261107_0004`)

| Table | Purpose |
|-------|---------|
| `app.signal_history` | Durable multi-agent signals; UNIQUE `decision_id`; UNIQUE `(owner_user_id, idempotent_key)` |
| `app.signal_agent_contributions` | Per-agent bias/confidence/indicators; FK → signal_history |
| `app.signal_risk_events` | Risk verdict history / veto timeline |
| `app.scheduler_evaluation_history` | Closed-candle checkpoint mirror |
| `app.scheduler_audit` | Engine audit mirror (`local_audit_id` unique per owner) |

Common columns: `owner_user_id` (required), UTC `timestamptz`, JSONB payloads, category check `spot|linear`.

## Keep local-only

| SQLite | Reason |
|--------|--------|
| `scheduler_lock` | Single-process lease; not a distributed lock service |
| `paper_risk_state` | Authoritative halt/cooldown until explicit SoT promotion |
| `cloud_sync_outbox` | Offline sync buffer (schema v3) |

## Future Phase 5 proposal (do not create live tables yet)

- `historical_candle_datasets` / `historical_candles` (separate spot vs linear datasets)
- `backtest_runs` / `backtest_trades` / `backtest_equity_points`
- `paper_trading_sessions` / `paper_orders` / `paper_fills` / `paper_positions`
- `trading_journal_entries`

Each future table must include `owner_user_id`, retention limits, and no credential columns.

## Retention guidance (personal use)

| Data | Suggested bound |
|------|-----------------|
| Signals | Soft cap via app pagination (200/page); archive later |
| Scheduler audit | Local already capped (~2000); cloud mirror similar |
| Outbox synced rows | Compact periodically after confirmed sync |

## Indexes

Owner+time, owner+symbol+interval+time, owner+strategy_version+time, eval stream key — see proposed Alembic file.
