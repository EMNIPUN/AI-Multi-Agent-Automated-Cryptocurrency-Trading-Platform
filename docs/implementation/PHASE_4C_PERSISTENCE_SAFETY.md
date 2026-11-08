# Phase 4C — Persistence Safety

## Storage path

Resolved by `resolve_signal_db_path()`:

1. Explicit constructor `db_path`, else
2. `MULTI_AGENT_SIGNALS_DB` / `SIGNAL_HISTORY_DB`, else
3. `<repo>/data/multi_agent_signals.sqlite3`

## Schema

- **v1:** `signal_history`, `paper_risk_state`, `schema_meta`
- **v2 (additive):** `evaluation_checkpoints`, `scheduler_lock`, `scheduler_audit`

Migrations are forward-only; existing history and risk halt flags are preserved.

## Fail-closed rules

| Failure | Behavior |
|---------|----------|
| Signal/risk write error | Actionable BUY/SELL → **BLOCKED** (`PERSISTENCE_FAILED`); in-memory risk reloaded from DB |
| Corrupt `seen_keys_json` | `SignalHistoryStoreError`; row marked `corrupt=1`, `halted=1` |
| Missing risk row | Fail closed / halted |
| DB lock / disk / transaction error | Raised as `SignalHistoryStoreError` — no soft-ignore |
| Second process engine start | `scheduler_lock` lease denied |
| Daily halt | Persisted; restart does **not** clear |

## Atomic write

`persist_decision_and_risk()` uses `BEGIN IMMEDIATE` to insert (or accept duplicate) the decision and update paper risk in one transaction.

## Checkpoint semantics

Checkpoint status `completed` is written **only after** a durable evaluate path without `PERSISTENCE_FAILED`. Crashes before checkpoint leave the candle eligible for retry (bounded backfill/poll).
