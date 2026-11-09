# CryptoNova 72 — Supabase-Only Audit

Development revision is `20261108_0011`. This runtime is not Supabase-only.

| Path | Runtime store | Silent SQLite fallback |
| --- | --- | --- |
| Signals | PostgreSQL when source-of-truth mode is on. Status fails closed with HTTP 409 when the owner is unset. | No. Offline SQLite is only when source-of-truth mode is explicitly off. |
| Paper broker | PostgreSQL when source-of-truth mode is on. Read API is off, so the HTTP path does not open it. | No for the store. Backtests use a separate explicit SQLite journal. |
| Paper analytics | Can read the paper store. Not verified against the three development sessions. | Same as paper. |
| Backtest journals | Isolated SQLite `bt68a_*.sqlite3`. | This is the active journal, not a fallback after a failed PostgreSQL write. |
| News | PostgreSQL repository. Refuses SQLite. | Archive writer rolls back only its savepoint if revision storage is missing, so the article transaction can commit. |
| Alerts | PostgreSQL when enabled. Flag is off. Count is 0. | No. |
| LLM audit | PostgreSQL `llm_evaluations`. Count is 0. | No provider call when storage is not ready. |
| LLM budget | PostgreSQL ledger. Live status reports durable storage. Count is 0. | Fail closed when the ledger is not ready. |
| News revisions | PostgreSQL append-only table. 2 rows exist. | Missing table does not invent a revision. |

`PostgresBacktestJournal` refuses SQLite. It is not wired, so a PostgreSQL failure cannot switch a backtest onto the paper tables.

Source-of-truth mode remains the default. A backtest no longer turns it off for the process.
