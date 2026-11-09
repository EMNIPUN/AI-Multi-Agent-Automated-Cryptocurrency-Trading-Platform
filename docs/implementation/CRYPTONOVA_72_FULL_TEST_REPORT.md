# CryptoNova 72 — Full Test Report

Skipped tests are not verified.

## Backend

`uv run pytest -q -rs --tb=no`

- Passed: 647
- Failed: 36
- Skipped: 1

The skip is `tests/test_core_news_69a1.py` because `NEWS_PG_INTEGRATION` is unset.

Prompt 72 tests in `tests/test_core_72_isolation.py`: 4 passed, 0 failed, 0 skipped. They cover log redaction, backtest isolation, the signal owner 409, and the unapplied journal rejecting SQLite.

`tests/test_core_backtest_68a.py` was included in an earlier 20-passed run with the isolation tests.

The 36 failures are in older phase 2–4 suites. Examples: migration audits that reject tables added by later milestones, and SQLite order/telemetry rows whose schema does not match the current ORM (`order_intents.owner_user_id`, telemetry `record` returning false). They failed in files collected before the new isolation test. They are not counted as prompt 72 regressions, and they are not counted as passing.

## Frontend

`npm test` in `apps/web`: 13 files passed, 59 tests passed, 0 failed, 0 skipped.

`npm run typecheck`: passed after the news dashboard type fix.

`npm run build`: passed, exit code 0.

## Not claimed

Cross-user RLS denial was not executed with a non-bypass role. PostgreSQL paper fill parity was not run. Signed-in dashboard data was not rendered. The news PostgreSQL integration test was skipped.
