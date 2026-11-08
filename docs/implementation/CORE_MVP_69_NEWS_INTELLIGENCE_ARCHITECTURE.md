# CryptoNova — News Intelligence Architecture (69)

| Field | Value |
| --- | --- |
| Stage | **69A + 69A.1 COMPLETE** (foundation + Supabase persistence) |
| 69B–69E | Not started — require explicit operator approval |
| Persistence target | Supabase PostgreSQL (`app` schema) |
| Trading impact | **None** in 69A/69A.1 (advisory storage + context snapshot only) |

## Pipeline (69A.1)

```
Providers (fixture / RSS / optional NewsData)
  → collector (validate → dedupe → classify)
  → PostgresNewsRepository (Supabase app.news_*; fail closed if unavailable)
  → FastAPI read API (+ gated POST /collect)
  → Next.js same-origin proxies
```

## Modules

| Path | Role |
| --- | --- |
| `agent/news/*` | Domain logic |
| `apps/api/app/news/*` | Gated FastAPI surface |
| `apps/api/alembic/versions/20261108_0007_news_foundation_69a.py` | Supabase tables + RLS |
| `apps/web/src/app/api/news/*` | Proxies |

## SQLite prerequisites (unchanged)

Paper journals, backtest `bt68a_*.sqlite3`, and offline signal SQLite paths remain. 69A does **not** migrate or delete them. News SoT is Supabase-only via migration 0007.

## Feature flags (default OFF)

`NEWS_READ_API_ENABLED`, `NEWS_COLLECTION_ENABLED`, `NEWS_ALERTS_ENABLED`, `NEWS_LLM_ENABLED`, `NEWS_AGENT_ADVISORY_ENABLED`

## Next stages

- **69B** Critical alerts + in-app notifications
- **69C** Wire NewsContext into Coordinator (still advisory unless separately approved)
- **69D** Optional OpenAI interpretation
- **69E** News-aware backtesting with availability timestamps
