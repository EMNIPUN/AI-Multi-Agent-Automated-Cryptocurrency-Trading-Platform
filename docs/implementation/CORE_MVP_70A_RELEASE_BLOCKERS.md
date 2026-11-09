# CryptoNova — 70A Release Blockers

The development MVP is not fully verified end to end.

## Must stay blocked until a separate approval

1. Apply `20261108_0008`, `0009`, `0010`, and `0011` on development project `wmirifmgaftassgrfbyl` only.
2. Do not enable `NEWS_ALERTS_ENABLED` before `0008`.
3. Do not enable `NEWS_LLM_ENABLED` before `0009` and `0011`. The service fail-closes without both the audit table and the budget ledger.
4. Do not enable `NEWS_TELEGRAM_ENABLED` or `NEWS_AUTO_COLLECTION_ENABLED`.
5. Do not set `AGENT_ALLOW_LIVE=true`.
6. Do not call OpenAI as part of a backtest or a dashboard load.

## Still true after those migrations

- News rows written before `0010` have no revision chain. They stay `historical_provenance=incomplete`. The writer does not invent those revisions.
- Paper trading and backtest journals still use isolated SQLite. That is intentional for offline simulation and is not retired.
- Signal history can still persist to local SQLite when Supabase SoT is off. Runtime SoT is configured toward Postgres, but this audit did not re-prove every paper and signal path against the live development database.
- `DATABASE_URL` bypasses RLS.
- LLM agreement and news conflicts are not profitability.
- `/news`, `/llm`, `/backtesting`, `/analytics`, paper, and signal pages were not clicked in a signed-in browser during this audit.
- Local `.env` has `BACKTEST_READ_API_ENABLED=true` and `BACKTEST_RUN_API_ENABLED=true`. Those gates start simulations only. They do not place live orders. News and LLM flags were not enabled in `.env`.

## Not a release

No production deploy, no production migration, and no live Bybit order path was exercised.
