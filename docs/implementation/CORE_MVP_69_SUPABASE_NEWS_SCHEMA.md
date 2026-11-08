# Supabase News Schema (69A)

Migration: `apps/api/alembic/versions/20261108_0007_news_foundation_69a.py`  
Schema: `app`

## Tables (69A)

| Table | Purpose |
| --- | --- |
| `news_sources` | Provider registry |
| `news_articles` | Deduped articles (`content_hash` PK) |
| `news_events` | Classified events |
| `news_event_assets` | Event ↔ symbol |
| `news_classifications` | Classifier payload audit |
| `news_ingestion_runs` | Collection run metadata |
| `news_provider_health` | Provider check history |

RLS: `*_select_own` for role `authenticated` (`owner_user_id IS NULL OR = auth.uid()`).

## Deferred to 69B+

`news_alerts`, `news_alert_deliveries`, `news_operator_preferences`, durable `news_agent_context` rows.

## Runtime note (69A.1)

FastAPI runtime uses `PostgresNewsRepository` against Supabase PostgreSQL only. In-memory storage is restricted to isolated unit tests via `reset_news_service_for_tests`. When Postgres/tables are unavailable, the API fails closed (`UnavailableNewsRepository`, HTTP 503) — never silent memory fallback. See `CORE_MVP_69A1_SUPABASE_NEWS_PERSISTENCE_REPORT.md`.
