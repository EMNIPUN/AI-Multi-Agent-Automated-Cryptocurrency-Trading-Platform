# CryptoNova — Supabase-Only Migration Report

**Status: BLOCKED. The platform is not Supabase-only.**

## What already uses Postgres when source-of-truth mode is on

`SUPABASE_SOT_ENABLED` defaults to true. `PaperStore` and `SignalHistoryStore` then call `create_agent_engine()`, which uses `DATABASE_URL` and ignores a SQLite path. Tables `paper_*` and `signal_history` already exist from earlier migrations. Development currently has 3 paper sessions and 0 signal-history rows.

Opening those stores still requires `SIGNAL_CLOUD_OWNER_USER_ID` or `CRYPTONOVA_TEST_OWNER_USER_ID`. Neither is set. `GET /api/v1/signals/status` returns 500 with `signal_cloud_owner_user_id_unset`. No owner id was invented.

The paper read API is disabled, so `/paper` does not open the three stored sessions.

## What still uses SQLite

| Use | Classification | Runtime selection |
| --- | --- | --- |
| `agent/backtest/store.py` `bt68a_*.sqlite3` | Backtest execution journal | `ensure_offline_sot()` sets `SUPABASE_SOT_ENABLED=false` for the process, then opens a new SQLite file |
| `PaperStore` / `SignalHistoryStore` under that flag | Same process after a backtest | Can fall back to SQLite for the rest of the process |
| Pytest paths such as `tmp_path / "paper.sqlite3"` | Offline fixtures | Used only when source-of-truth mode is off |
| `data/multi_agent_signals.sqlite3` | Legacy local journal path | Not deleted |

`ensure_offline_sot()` is intentional isolation: a backtest must not write into the user's paper sessions. Removing it without a separate Postgres run namespace would mix simulated fills into live paper rows. That cutover is not approved and was not performed.

No SQLite file was deleted. No new Alembic revision was created, because the paper and signal tables already exist. A future backtest-journal migration needs its own approval, a backup, and a parity suite before any cutover.

## Parity not claimed

Fills, balances, fees, and analytics were not compared between the SQLite backtest journal and Postgres in this pass. Until that comparison passes, the SQLite backtest journal stays the isolated execution store.
