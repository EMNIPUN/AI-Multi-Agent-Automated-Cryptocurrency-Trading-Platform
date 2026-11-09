# CryptoNova — Paper, Signal, and Backtest Parity

**Status: BLOCKED. Parity was not run, and no cutover was performed.**

## Paper

`PaperStore` writes Postgres when source-of-truth mode is on, using the existing `app.paper_*` tables. Development has 3 sessions, 0 orders, and 0 fills. The paper read API is disabled, so those sessions were not rendered. No new fills were created. SQLite paper fixtures under tests were not deleted.

## Signals

`SignalHistoryStore` also targets Postgres in source-of-truth mode. `signal_history` has 0 rows. The status route fails closed because no cloud owner id is configured. The previous process could answer only when that requirement was not hit. This restart uses current source and returns 500. That is not a successful migration.

## Backtests

`open_isolated_paper_store()` forces `SUPABASE_SOT_ENABLED=false` and creates `bt68a_*.sqlite3`. That keeps a backtest out of the user's paper sessions. It also changes the process environment, so a later request in the same API process can see source-of-truth mode as off. Replacing that journal with Postgres requires a run-scoped schema and a parity check of fills, fees, balances, and result hashes. None of that was executed.

No source journal was hashed, imported, or removed in this pass.
