# CryptoNova — Prompt 69A.1 Supabase News Persistence Report

| Field | Value |
| --- | --- |
| Prompt | **69A.1** — Complete Supabase news persistence |
| Date | 2026-11-08 |
| Status | **COMPLETE** (development target migrated; runtime fail-closed) |
| Next | **69B** not started — stop here |

---

## 1. Database schema verification

Migration: `apps/api/alembic/versions/20261108_0007_news_foundation_69a.py`  
Schema: `app`

| Table | Keys / constraints | Indexes | Notes |
| --- | --- | --- | --- |
| `news_sources` | PK `provider_id` | — | Provider registry + `meta_json` |
| `news_articles` | PK `content_hash`; UNIQUE `(provider_id, external_id)` | `ingested_at_ms` | Deduped articles; ms epoch fields |
| `news_events` | PK `event_id` | `available_at_ms`; `(severity, available_at_ms)` | Classified events |
| `news_event_assets` | PK `(event_id, symbol)`; FK → `news_events` CASCADE | `symbol` | Event ↔ symbol |
| `news_classifications` | PK `id`; FK → `news_events` CASCADE | — | Classifier audit trail |
| `news_ingestion_runs` | PK `run_id` | — | Collection run metadata |
| `news_provider_health` | PK `id` | `(provider_id, checked_ms)` | Provider check history |

**Timestamps:** event/article timing uses UTC epoch milliseconds (`*_at_ms`); row `created_at` uses `timestamptz` `now()`.

**Idempotent upserts:** repository upserts articles by `(provider_id, external_id)` (then `content_hash`), sources by `provider_id`, events by `event_id`, runs with `ON CONFLICT DO NOTHING` on `run_id`.

**Foreign keys:** `news_event_assets.event_id` and `news_classifications.event_id` → `news_events` with `ON DELETE CASCADE`.

**RLS / least privilege:** each table `ENABLE ROW LEVEL SECURITY` with `*_select_own` for role `authenticated` (`owner_user_id IS NULL OR owner_user_id = auth.uid()`). No `GRANT` of schema `USAGE` to `anon`/`authenticated` in this migration (matches prior catalog pattern). FastAPI uses privileged `DATABASE_URL` (bypasses RLS) and must keep application filters/gates as primary authorization. Write policies for runtime least-privilege roles remain deferred (Option A / Gate 63 track).

**SQLite:** not used for news. `PostgresNewsRepository` rejects `sqlite` dialect.

---

## 2. Migration application status and target environment

### Preflight (required)

| Check | Result |
| --- | --- |
| `CRYPTONOVA_DB_TARGET` | `development` |
| `CRYPTONOVA_DEV_PROJECT_REF` | `wmirifmgaftassgrfbyl` (approved allowlist) |
| Connection host | `aws-0-ap-southeast-2.pooler.supabase.com` (session pooler) |
| Identity guard | `ok` |
| Production apply | **Not performed** |

### Plan (delta applied online)

Online DB was at `20261108_0006`. Offline SQL plan for `20261108_0006 → 20261108_0007` creates the seven `app.news_*` tables, indexes, RLS enablement, and seven `*_select_own` policies, then stamps `app.alembic_version` to `20261108_0007`.

### Apply status

| Environment | Revision before | Action | Revision after |
| --- | --- | --- | --- |
| Approved **development** Supabase (`wmirifmgaftassgrfbyl`) | `20261108_0006` | `alembic upgrade head` (operator-gated) | `20261108_0007` (head) |
| Production | n/a | **Not applied** | unchanged |

`.env` keeps `CRYPTONOVA_ALLOW_DEV_MIGRATIONS=false` by default; apply used an explicit session override after identity verification.

---

## 3. Repository implementation

| Component | Path | Role |
| --- | --- | --- |
| Protocol + in-memory (tests only) | `agent/news/repository.py` | `InMemoryNewsRepository` (`storage_kind=memory_test_only`) |
| Postgres adapter | `apps/api/app/news/pg_repository.py` | `PostgresNewsRepository` — transactional `persist_collection`, upserts, reads |
| Fail-closed stub | `apps/api/app/news/unavailable_repository.py` | Raises `NewsStorageError` on all ops; `ping()→False` |
| ORM models | `apps/api/app/persistence/news_models.py` | SQLAlchemy models under schema `app` |
| Runtime wiring | `apps/api/app/news/state.py` | Builds PG repo or `UnavailableNewsRepository`; **never** silent memory fallback |
| Service | `agent/news/service.py` | Refuses collection when storage unavailable; surfaces `storage_*` in status |

Runtime path: `create_db_engine()` → `PostgresNewsRepository` → `ping()` requires `SELECT` on `app.news_articles`. On missing tables / unreachable DB → `UnavailableNewsRepository` + explicit `storage_error`.

---

## 4. Runtime configuration

| Flag / setting | Default | Notes |
| --- | --- | --- |
| `DATABASE_URL` | required for runtime PG | Supabase Postgres only for news SoT |
| `NEWS_READ_API_ENABLED` | `false` | Gated GET surface |
| `NEWS_COLLECTION_ENABLED` | `false` | Gated POST `/collect` |
| `NEWS_ALERTS_ENABLED` | `false` | 69B — off |
| `NEWS_LLM_ENABLED` | `false` | 69D — off |
| `NEWS_AGENT_ADVISORY_ENABLED` | `false` | 69C — off |
| `NEWS_RSS_FEED_URLS` / `NEWSDATA_API_KEY` | optional | Providers; fixture used when none configured |

Status payload includes `storage_kind`, `storage_available`, `storage_error`. Collect/read endpoints return **503** `storage_unavailable` when PG is down. GET never triggers collection.

---

## 5. Persistence and restart tests

| Scenario | Result |
| --- | --- |
| Article/event/run persist via `persist_collection` | Pass (live PG integration) |
| Process-restart simulation (new `PostgresNewsRepository` instance) | Pass — prior run readable by `owner_user_id` |
| Duplicate provider/external_id re-ingest | Pass — upsert, no UniqueViolation |
| Storage down → collect/articles | Pass — 503 + `storage_unavailable` |
| SQLite engine rejected | Pass — `sqlite_forbidden` |
| GET does not collect | Pass (69A suite) |

Live check: `PostgresNewsRepository.ping() → True` after migration on development.

---

## 6. Security / RLS verification

| Control | Status |
| --- | --- |
| RLS enabled on all `app.news_*` | Yes (migration) |
| SELECT policies for `authenticated` | Yes (`*_select_own`) |
| Loopback / operator local gates on news API | Preserved (`require_news_local_access`, collect gate) |
| Feature flags default OFF | Yes |
| No live orders / OpenAI / agent advisory wiring | Confirmed — flags false; `places_orders=false` |
| Privileged DB role bypasses RLS | Documented; app gates remain mandatory |
| Runtime write RLS for least-privilege DB role | **Deferred** (Option A / Gate 63) |

---

## 7. Existing SQLite dependencies (unchanged)

69A.1 does **not** migrate or rewrite these paths:

| Dependency | Still used for |
| --- | --- |
| Paper broker journals / local paper SQLite engines under `SUPABASE_SOT_ENABLED=false` test harness | Paper trading tests & offline sims |
| Backtest isolated journals `bt68a_*.sqlite3` | 68A/68C backtest runs |
| Offline signal history SQLite in phase-4 tests | Signal store unit tests |

**Remaining migration dependencies (separate milestones):** full paper SoT cutover verification under `SUPABASE_SOT_ENABLED=true` in all environments; optional retirement of offline SQLite test engines; Gate 63 credential/role cutover; backtest artifact store remains filesystem + ephemeral journals by design.

---

## 8. Test results

### News unit + fail-closed (no live PG flag)

```
uv run pytest tests/test_core_news_69a.py tests/test_core_news_69a1.py -q
→ 21 passed, 1 skipped
```

Skipped: `test_postgres_integration_persist_and_restart` (requires `NEWS_PG_INTEGRATION=1`).

### News + live development PG

```
NEWS_PG_INTEGRATION=1 uv run pytest tests/test_core_news_69a.py tests/test_core_news_69a1.py -q
→ 22 passed, 0 skipped
```

### Regression (paper + backtest)

```
uv run pytest tests/test_core_paper_broker.py tests/test_core_backtest_68a.py -q
→ 43 passed
```

| Suite | Passed | Failed | Skipped |
| --- | ---: | ---: | ---: |
| News (default) | 21 | 0 | 1 |
| News (`NEWS_PG_INTEGRATION=1`) | 22 | 0 | 0 |
| Paper broker + backtest 68A | 43 | 0 | 0 |

---

## 9. Remaining blockers

| Item | Severity | Notes |
| --- | --- | --- |
| Production migration of 0007 | Operator | Must not auto-apply; separate prod identity + approval |
| `CRYPTONOVA_ALLOW_DEV_MIGRATIONS` left `false` in `.env` | Intentional | Prevents accidental re-apply |
| Runtime DB least-privilege role + write RLS | Deferred | Option A / Gate 63 |
| News → alerts / dashboard / trading decisions | Out of scope | 69B–69E |
| Shared-dev fixture rows under `owner_user_id IS NULL` | Low | Harmless advisory demo data; clean optionally |

---

## 10. Readiness for 69B

**Ready to begin 69B (Critical Alert Engine) when explicitly approved.**

Prerequisites met for 69B design:

- Durable `app.news_*` SoT on development Supabase
- Fail-closed runtime repository (no silent memory)
- Classified events + NewsContext read path available
- Alerts / LLM / advisory / live trading still OFF

69B must **not** enable live exchange execution, OpenAI news LLM, or automatic trading-signal mutation without separate approval.

**Stop after 69A.1 — 69B not started.**
