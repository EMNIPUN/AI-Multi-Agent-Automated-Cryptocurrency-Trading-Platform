# CryptoNova — Prompt 69B Critical Alert Engine Report

| Field | Value |
| --- | --- |
| Prompt | **69B** |
| Date | 2026-11-08 |
| Status | **COMPLETE** (code + tests). Migration `20261108_0008` is **not applied** |
| Next | **69C not started** |

## 1. Schema

New revision `apps/api/alembic/versions/20261108_0008_news_alerts_69b.py` revises `20261108_0007`.

| Table | Role |
| --- | --- |
| `app.news_alerts` | Alert rows, idempotency key, evidence, agent context |
| `app.news_alert_deliveries` | In-app and Telegram attempts; unique delivery key |
| `app.news_alert_preferences` | Min severity, symbols, cooldown, ttl, channel flags |
| `app.news_collection_lease` | Single-owner poll lease |

RLS: `ENABLE ROW LEVEL SECURITY` and `{table}_select_own` for `authenticated` (`owner_user_id IS NULL OR owner_user_id = auth.uid()`). Existing `app.news_*` foundation tables are unchanged.

## 2. Migration status

| Target | Action |
| --- | --- |
| Development `wmirifmgaftassgrfbyl` | **Not applied.** `.env` has `CRYPTONOVA_ALLOW_DEV_MIGRATIONS=false`. 69B requires operator approval before `alembic upgrade`. |
| Production | **Not applied** |

Plan, after approval only:

1. `CRYPTONOVA_DB_TARGET=development`
2. `CRYPTONOVA_DEV_PROJECT_REF=wmirifmgaftassgrfbyl`
3. `CRYPTONOVA_USE_DATABASE_URL_AS_DEV=true`
4. `CRYPTONOVA_ALLOW_DEV_MIGRATIONS=yes` for that shell only
5. `uv run alembic -c apps/api/alembic.ini upgrade 20261108_0008`

Until then, article storage from 69A.1 still works. Alert writes fail closed with `alerts_schema_unavailable` if `NEWS_ALERTS_ENABLED=true`.

## 3. Engine

`agent/news/alerts/engine.py` scores category, assets, magnitude phrases, verification, corroboration, freshness, provider delay, and uncertainty. Sentiment does not set severity or direction. Negative copy alone stays below the default HIGH threshold.

Dedup: same `event_id` + material fingerprint is suppressed. A headline, severity, or verification change is a material update and may alert inside cooldown. Other same-symbol/category events respect cooldown unless severity rises. Stale and delayed items carry warnings and are not described as realtime.

## 4. Runtime

- `InMemoryAlertRepository` — tests only
- `PostgresAlertRepository` — Supabase, rejects SQLite
- Collection persists alerts only when `NEWS_ALERTS_ENABLED=true` and `app.news_alerts` answers
- Telegram adapter is off unless token and chat id exist; confirmation requires HTTP 2xx
- `NEWS_AUTO_COLLECTION_ENABLED=false`. Scheduler code uses the DB lease and does not start by default. Manual `POST /collect` remains the supported path. Feeds are polled, not realtime

## 5. API and UI

See `CORE_MVP_69B_ALERT_API_CONTRACT.md`, `CORE_MVP_69B_TELEGRAM_NOTIFICATION_CONTRACT.md`, and `CORE_MVP_69B_NEWS_DASHBOARD_REPORT.md`.

`/news` and the dashboard unread strip read the API. They do not fabricate alerts.

## 6. Safety

Unchanged and default off: `NEWS_LLM_ENABLED`, `NEWS_AGENT_ADVISORY_ENABLED`, `AGENT_ALLOW_LIVE`. No Coordinator, Risk, or SignalPipeline edits. No live orders. No production migration. No Telegram calls in tests.

## 7. Tests

```
uv run pytest tests/test_core_news_69a.py tests/test_core_news_69a1.py tests/test_core_news_69b.py tests/test_core_paper_broker.py tests/test_core_backtest_68a.py -q
→ 76 passed, 1 skipped, 0 failed
```

The skip is the optional live Postgres news integration (`NEWS_PG_INTEGRATION` unset). `apps/web` vitest `news-format.test.ts`: 3 passed. Paper and backtest SQLite journals were not migrated.

## 8. Readiness for 69C

Alert `agent_context` is stored and returned. It is not wired into trading decisions. 69C can read it later. **69C was not started.**
