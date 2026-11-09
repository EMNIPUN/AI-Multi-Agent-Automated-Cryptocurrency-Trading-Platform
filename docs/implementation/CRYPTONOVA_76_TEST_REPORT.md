# CryptoNova 76 — Test Report

Local evidence only. Development Supabase was not migrated and was not written.

## Backend

Acceptance command: `uv run pytest -q -rs --tb=line`

- Passed: 695
- Failed: 0
- Skipped: 1
- Duration: 195.65s
- Exit code: 0

An earlier full run in the same phase, collected before the ETH and 60-minute parity test was added, finished 694 passed, 0 failed, 1 skipped. The acceptance count above includes that extra test.

### Skip

`tests/test_core_news_69a1.py:116`

Reason: `Set NEWS_PG_INTEGRATION=1 with migrated development DATABASE_URL to run`

The flag stayed unset. Enabling it would persist fixture news under a generated owner on the development database. The skip is intentional.

### Local PostgreSQL tests included in the 695

- `test_migration_0012_checksum_is_unchanged`
- `test_postgres_journal_mode_fails_closed_without_sqlite_fallback`
- `test_migration_0012_upgrade_and_downgrade_on_localhost`
- `test_eth_and_second_timeframe_sqlite_matches_local_postgres`
- `test_sqlite_backtest_matches_local_postgres_journal`
- Existing localhost RLS harness when port `55432` is up

Those tests use `127.0.0.1:55432`. They are not development Supabase validation. Disposable databases were dropped.

### Not run

- Development Alembic upgrade or downgrade
- Development paper, signal, or news writes
- Paid OpenAI calls
- Telegram delivery
- Automatic news collection
- Live Bybit orders
- Signed-in browser session

## Frontend

- Vitest: 13 files, 59 passed, 0 failed
- `npm run typecheck` (`tsc --noEmit`): exit 0
- `npm run build` (`next build`): exit 0, 33 static pages

## Analytics reconciliation

`tests/test_core_paper_analytics.py` covers win rate, loss rate through outcome classification, profit factor, expectancy, realized and unrealized treatment, fees, equity curve, drawdown, and symbol breakdowns. `test_open_positions_excluded` and `test_fee_treatment_no_double_count` keep open-position entry fees out of closed-trade performance.

The BTC 15-minute journal comparison asserts `Decimal` closed-trade `total_fees <=` the sum of persisted fill fees. The previously measured pair on that fixture was closed-trade fees `40.22621097` and fill fees `50.34005213`. That gap is an expected representation difference. No rounding was introduced to hide it. Strategy decisions were not changed.

## Regressions

No new failing test remained at the end of the acceptance run. No trading assertion was weakened.

## Development catalog

Read-only session before local work and the same read-only session after local work:

| Item | Before | After |
| --- | --- | --- |
| Alembic revision | `20261108_0011` | `20261108_0011` |
| `app.backtest_exec_runs` | absent | absent |
| Paper sessions | 3 | 3 |
| Paper orders | 0 | 0 |
| Paper fills | 0 | 0 |
| Signal history | 0 | 0 |
| News events | 10 | 10 |
| News revisions | 2 | 2 |

The privileged role still bypasses RLS. That was observed, not changed.
