# CryptoNova — Prompt 69C News Agent Communication Report

| Field | Value |
| --- | --- |
| Prompt | **69C** |
| Status | **COMPLETE** as advisory observability |
| Trading impact | None. `news_changed_decision` is always false |
| Next | **69D not started** |

## Migration 0008

Read-only check on development project `wmirifmgaftassgrfbyl`: Alembic current is `20261108_0007`. `20261108_0008` remains **not applied**. This prompt did not run `alembic upgrade`. Approval steps, for a later operator session only:

1. Confirm `CRYPTONOVA_DB_TARGET=development`
2. Confirm `CRYPTONOVA_DEV_PROJECT_REF=wmirifmgaftassgrfbyl`
3. Confirm `CRYPTONOVA_USE_DATABASE_URL_AS_DEV=true`
4. Set `CRYPTONOVA_ALLOW_DEV_MIGRATIONS=yes` in that shell only
5. `uv run alembic -c apps/api/alembic.ini current` then `upgrade 20261108_0008`

Do not point those commands at production. 69C does not turn on `NEWS_ALERTS_ENABLED` or `NEWS_AGENT_ADVISORY_ENABLED` to hide a missing alert schema.

No new Alembic revision was added. The advisory summary rides the existing decision public payload (`news_advisory`, source event ids, freshness, warnings). Full article text is not copied into the signal record.

## Pipeline

Optional `news_advisory_enabled` on `SignalPipeline.evaluate` defaults to false. A loader exception becomes an unavailable context and the technical decision still returns. Agents record an observation only when that flag is on and the adapter runs.

## UI

Signal panel and `/news` show **News Advisory Only — Trading Decisions Unchanged**. No LLM recommendation is rendered.

## Tests

```
uv run pytest tests/test_core_news_69a.py tests/test_core_news_69a1.py tests/test_core_news_69b.py tests/test_core_news_69c.py tests/test_phase4a_multi_agent_signals.py tests/test_core_paper_broker.py tests/test_core_backtest_68a.py -q
→ 98 passed, 1 skipped, 0 failed
```

The skip is the optional live Postgres news integration. Web `news-format.test.ts`: 4 passed.

## Safety

`NEWS_LLM_ENABLED=false`, `NEWS_AGENT_ADVISORY_ENABLED=false`, `AGENT_ALLOW_LIVE=false`. No live orders. No risk-threshold or position-size changes.
