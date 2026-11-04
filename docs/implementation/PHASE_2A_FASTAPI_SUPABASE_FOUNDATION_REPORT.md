# Phase 2A — FastAPI + Supabase PostgreSQL Foundation

| Field | Value |
|-------|-------|
| Date | 2026-11-04 |
| Scope | Read-only FastAPI app + version-controlled Postgres schema |
| Exchange | **Not called** (Bybit remains CLI/`agent` only) |
| Database | Models + Alembic prepared for Supabase Postgres; **not** auto-applied remotely |
| Execution SoT | Local SQLite (`order_intents` / `order_executions` / risk) — unchanged |
| Constraints | Offline pytest; no Bybit/Supabase network from tests; no commit/push; no `.env` secret edits |

---

## Created / modified files

### Created

| Path | Role |
|------|------|
| `apps/api/main.py` | ASGI entry (`apps.api.main:app`) |
| `apps/api/app/factory.py` | App factory, CORS (explicit origins only), routers |
| `apps/api/app/config.py` | Server-side settings (`DATABASE_URL`, bind host, SSL) |
| `apps/api/app/db.py` | SQLAlchemy engine/session helpers |
| `apps/api/app/models.py` | `app.agent_decisions`, `app.system_events`, `app.strategy_configs` |
| `apps/api/app/schemas.py` | Public Pydantic responses |
| `apps/api/app/deps.py` | Settings + reserved DB/auth gates |
| `apps/api/app/errors.py` | Safe error helpers |
| `apps/api/app/routers/health.py` | `GET /health` |
| `apps/api/app/routers/system.py` | `GET /api/v1/system/status` |
| `apps/api/alembic.ini` | Alembic config (manual apply) |
| `apps/api/alembic/env.py` | Requires real `DATABASE_URL`; SSL connect args for remote |
| `apps/api/alembic/versions/20261104_0001_initial_app_schema.py` | Initial migration (upgrade + downgrade tables) |
| `tests/test_api_foundation.py` | Offline API + schema tests |
| `docs/implementation/PHASE_2A_FASTAPI_SUPABASE_FOUNDATION_REPORT.md` | This report |

### Updated

| Path | Change |
|------|--------|
| `apps/api/README.md` | Runbook + safety notes |
| `pyproject.toml` / `uv.lock` | FastAPI, uvicorn, SQLAlchemy, Alembic, psycopg, pydantic-settings, httpx |
| `requirements.txt` / `requirements-dev.txt` | Mirrored fallback pins |
| `.env.example` | Placeholder `DATABASE_URL` / API bind / CORS (no secrets) |
| `README.md` | How to start API locally |
| `docs/architecture/REPOSITORY_STRUCTURE.md` | Notes Phase 2A API existence |

**Not modified for trading behavior:** `bot/` execution paths, Phase 1 SQLite ledgers, CLI entrypoints (`main.py`, `run_agent.py`, `test_connection.py`). No Next.js init.

---

## Backend architecture

```text
Client (loopback)
  → uvicorn apps.api.main:app (127.0.0.1)
    → FastAPI factory
      → GET /health          (no DB, no Bybit)
      → GET /api/v1/system/status  (env labels only)
      → GET /api/v1/private/disabled  (401 stub)
    → SQLAlchemy models (schema `app`) — unused by public routes
    → Alembic (manual) → Supabase PostgreSQL
```

Authoritative execution/risk remains in **local SQLite**. Postgres tables are observational / configuration for future dashboards — **not** a second order ledger in 2A.

---

## Endpoints and authorization

| Method | Path | Auth | Side effects | Notes |
|--------|------|------|--------------|-------|
| GET | `/` | None | None | Discovery JSON |
| GET | `/health` | None | None | Liveness |
| GET | `/api/v1/system/status` | None | None | Non-sensitive status |
| GET | `/api/v1/private/disabled` | Required (stub) | None | Always **401** until auth exists |

**Not implemented (by design):** create/cancel order, leverage, live-agent toggle, emergency reset, balances, positions, intents, journals, risk records.

OpenAPI/docs exposed only when `API_DEBUG=true`.

---

## PostgreSQL schema and migration plan

### Schema `app`

| Table | Purpose |
|-------|---------|
| `agent_decisions` | Optional decision/audit mirror (symbol, action, signal_id, payload_json) |
| `system_events` | Operational events (severity, event_type, message) |
| `strategy_configs` | Named non-secret strategy parameter documents |

Indexes on `(env_scope, created_at)`, symbol/time, `signal_id`, `event_type`, unique `strategy_configs.name`.

### Migration

- Revision: `20261104_0001`
- Creates schema `app` + three tables + indexes
- Downgrade drops tables/indexes; leaves schema `app` (no `DROP SCHEMA CASCADE`)
- Alembic version table intended under schema `app`
- **Do not** auto-run against remote Supabase from app startup or CI in this phase

### Future tenancy / RLS (not implemented)

- Columns `env_scope` + `account_fp` are isolation hooks (fingerprint only — no API keys).
- Later: Supabase Auth JWT → `auth.uid()` mapping to tenant rows; enable RLS policies per table so the `anon`/`authenticated` roles cannot cross tenants.
- Service-role key must remain **server-only**; never `NEXT_PUBLIC_*`.
- Syncing SQLite intents/executions into Postgres requires an explicit Phase 2B+ design (idempotent upsert, no dual-write authority).

---

## Configuration and secret handling

| Variable | Where | Notes |
|----------|-------|-------|
| `DATABASE_URL` | Server `.env` only | Placeholder in `.env.example`; require `sslmode=require` for remote |
| `DATABASE_SSL_REQUIRE` | Server | Default `true`; forced `sslmode=require` for non-localhost |
| `API_HOST` | Server | Default `127.0.0.1`; `0.0.0.0` coerced back to loopback |
| `API_CORS_ORIGINS` | Server | Explicit list; `*` rejected → CORS off |
| Bybit keys | Existing bot `.env` | Not read by public status beyond env **labels** |
| Supabase service role | Not introduced | — |

No passwords hardcoded. Public status never returns connection strings or key material.

---

## How to start FastAPI locally

```powershell
uv sync --group dev
uv run uvicorn apps.api.main:app --host 127.0.0.1 --port 8000
```

`DATABASE_URL` may be empty — `/health` and `/status` still work.

---

## How to connect Supabase later (without sharing secrets)

1. Create a Supabase project; copy the **pooler/DB password** only into local/server secret store.
2. Set server-side:
   `DATABASE_URL=postgresql+psycopg://…?sslmode=require`
3. Review `apps/api/alembic/versions/20261104_0001_*.py`.
4. Apply **manually** from a trusted machine:
   `uv run alembic -c apps/api/alembic.ini upgrade head`
5. Never commit `.env`, never put DB URL in frontend env, never paste passwords into chat/docs.

---

## Test results

```text
uv run pytest -q
117 passed
```

Includes prior Phase 1A–1E suite + new `tests/test_api_foundation.py` (13 cases).

- No Bybit network from tests
- No Supabase connection required
- `.env` and `data/*.sqlite3` remain gitignored

---

## Risks and outstanding work (Phase 2B+)

1. **AuthN/AuthZ** — JWT/API keys, role model, before any private data routes.
2. **RLS policies** on `app.*` for multi-tenant SaaS.
3. **Optional sync** of SQLite intents/executions/risk → Postgres (read replicas / projections only; keep fail-closed SoT clear).
4. **Worker** (`apps/worker`) to run agent loop outside CLI.
5. **Read APIs** for decisions/events once auth exists.
6. **Control-plane** cancel/flatten — explicit operator actions with audit; still forbidden as casual HTTP.
7. Alembic `version_table_schema=app` requires schema to exist before first stamp on some setups — initial revision creates schema first.
8. Starlette/httpx TestClient deprecation warning (non-blocking).

---

## Acceptance checklist

| Criterion | Status |
|-----------|--------|
| FastAPI imports | Pass (`apps.api.main:app`) |
| Offline health/status tests | Pass |
| Postgres models + reversible migration prepared | Pass |
| CLI entry points intact | Pass |
| No private account data without auth | Pass |
| Phase 1 safety codepaths not rewritten for trading | Pass |
| Offline suite green | **117 passed** |
| No auto remote Supabase migrate | Pass |
| No live trading toggles via HTTP | Pass |
