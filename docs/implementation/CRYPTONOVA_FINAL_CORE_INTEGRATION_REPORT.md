# CryptoNova — Final Core Integration Report

Date: 2026-11-08. Development project `wmirifmgaftassgrfbyl` only. Production was not contacted.

## Verified baseline

| Check | Result |
| --- | --- |
| Identity | development, session pooler `aws-0-ap-southeast-2.pooler.supabase.com` |
| Alembic revision | `20261108_0011` |
| Migration gate in `.env` | false |
| `news_events` | 10 |
| `news_event_revisions` | 2 test rows for `70b1evt26a00b9fa389` |
| `news_alerts`, `llm_evaluations`, `llm_budget_ledger` | 0 |
| `paper_sessions` | 3 |
| `signal_history` | 0 |

Migrations `0008` through `0011` were already applied under Master Prompt 70B.1. This prompt did not apply them again and did not add a new revision.

## What changed in this pass

- `/api/v1/backtests/shadow-status` reads `app.alembic_version`. On this database it returns revision `20261108_0011`, an empty pending list, and `historical_news_backtest_valid=false`.
- The LLM budget snapshot reads the ledger. Live status returned storage `postgres`, durable accounting true, daily budget 1.0, and zero calls this hour. The provider was not called.
- The LLM page shows remaining budget and calls this hour from that payload.

## Component status

| Area | Status |
| --- | --- |
| Alert persistence | Verified earlier against these tables. The engine flag stays off. |
| LLM audit and budget | Ledger and audit tables exist. Status is live. No paid call. |
| New revision capture | Verified for one synthetic event. Older events were not backfilled. |
| News-aware performance claims | Not valid. |
| Paper and signal runtime | Postgres tables exist. Signal status returns 500 until an owner id is set. |
| Backtest journals | Still isolated SQLite. |
| Signed-in dashboards | Not opened. No browser session. |

Live trading, Telegram, automatic collection, and LLM decisioning stay off.
