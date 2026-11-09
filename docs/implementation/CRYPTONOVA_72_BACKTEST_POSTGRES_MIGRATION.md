# CryptoNova 72 — Backtest PostgreSQL Migration

## Process isolation

`ensure_offline_sot()` no longer sets `SUPABASE_SOT_ENABLED` or clears the settings cache. `open_isolated_paper_store` and `open_isolated_read_store` open one SQLite file with `isolated_sqlite=True`. That flag does not change the engine used by paper or signal stores.

`test_backtest_journal_does_not_change_process_sot` opens a journal while source-of-truth mode is true and asserts the environment and `supabase_sot_enabled()` stay true while the journal dialect is SQLite.

Backtest fills stay in `bt68a_*.sqlite3`. They are not written to `app.paper_sessions`. Existing SQLite files were not deleted. Concurrent runs use distinct file names.

## Migration `20261108_0012`

File: `apps/api/alembic/versions/20261108_0012_backtest_exec_journal_72.py`.

Down revision: `20261108_0011`. Not applied. Live revision remains `20261108_0011`. `app.backtest_exec_runs` is absent.

Tables in the unapplied migration:

- `backtest_exec_runs` (config JSON, dataset hash, result hash)
- `backtest_exec_orders`
- `backtest_exec_fills`
- `backtest_exec_equity`

Each has select-own RLS for `authenticated`. The runner does not call `PostgresBacktestJournal`. That class rejects SQLite and does not fall back.

Parity against the SQLite simulator was not run, because the tables do not exist yet. Cutover is blocked.

## Approval required

Approve applying CryptoNova migration `20261108_0012` to the verified development project `wmirifmgaftassgrfbyl` only, after a fresh backup. Approval does not authorize deleting SQLite journals or switching the runner.
