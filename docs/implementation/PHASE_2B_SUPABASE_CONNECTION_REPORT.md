# Phase 2B — Supabase Connection, Migration Bootstrap & Schema Privacy

| Field | Value |
|-------|-------|
| Date | 2026-11-04 |
| Scope | Secure `DATABASE_URL` handling, Alembic bootstrap fix, schema privacy plan |
| Remote DB | **Not contacted** in this phase (no live migrate without explicit user approval) |
| Exchange | Not contacted |
| Execution SoT | Local SQLite unchanged |
| Offline suite | **128 passed** |

---

## Files changed

| Path | Change |
|------|--------|
| `apps/api/app/database_url.py` | **New** — normalize/redact/inspect URLs (psycopg, SSL, pooler hints) |
| `apps/api/app/config.py` | Uses URL helpers; safer errors; version `0.2.1-phase2b` |
| `apps/api/app/db.py` | No URL logging; `DatabaseUrlError` without secret context |
| `apps/api/app/migration_audit.py` | **New** — offline model↔migration audit |
| `apps/api/alembic/env.py` | **Bootstrap** `CREATE SCHEMA app` before `app.alembic_version`; include filters |
| `apps/api/alembic/versions/20261104_0001_*.py` | Comment clarifying idempotent schema create |
| `apps/api/sql/revoke_public_api_access.sql` | **New** — manual revoke of PUBLIC/anon/authenticated |
| `apps/api/README.md` | Connection modes + optional live checklist |
| `apps/api/__init__.py` | Version bump |
| `.env.example` | Direct vs Session pooler placeholders (no secrets) |
| `tests/test_supabase_phase2b.py` | **New** offline tests |
| `docs/implementation/PHASE_2B_SUPABASE_CONNECTION_REPORT.md` | This report |

Trading engine / SQLite ledgers / Bybit settings: **not modified**.

---

## Configuration

- Server-side `DATABASE_URL` only (gitignored `.env`).
- Normalized to `postgresql+psycopg://`.
- Remote hosts: `sslmode=require` enforced when `DATABASE_SSL_REQUIRE=true` (default).
- Localhost / `127.0.0.1` / `::1` skip forced SSL.
- Userinfo percent-encoding normalized; passwords with `@`/`:` must be URL-encoded by the operator.
- Soft classification of Direct / Session pooler / Transaction pooler from host+port (**no hardcoded project hosts**).
- Prefer **Session pooler (5432)** or **Direct** for Alembic; transaction pooler (6543) discouraged for migrations.
- Redaction helper for operator messages (`user:***@host`); never print raw URLs in app logs.
- No `NEXT_PUBLIC_` database credentials introduced.

---

## Migration bootstrap verification

### Issue (Phase 2A residual)

With `version_table_schema=app`, Alembic creates `app.alembic_version` **before** revision `upgrade()` runs. On a **fresh** database where schema `app` does not exist, that fails.

### Fix (Phase 2B)

`apps/api/alembic/env.py`:

1. Online: `CREATE SCHEMA IF NOT EXISTS app` + `commit` **before** `context.configure` / `run_migrations`.
2. Offline (`--sql`): emit the same `CREATE SCHEMA` before migration SQL.
3. `include_name` / `include_object` restrict scope to schema `app` (no auth/storage/realtime).
4. Initial revision still includes idempotent `CREATE SCHEMA IF NOT EXISTS app`.

### Model ↔ migration audit (offline)

`audit_initial_migration()` confirms:

- Tables: `app.agent_decisions`, `app.system_events`, `app.strategy_configs`
- Columns and indexes from SQLAlchemy models appear in revision source
- No FK to non-`app` schemas
- No `DROP SCHEMA … CASCADE` executable statements
- No touch of Supabase-managed schemas in migration text

`Base.metadata.create_all` is **not** used as a migration substitute (`db.py` has no `create_all`).

---

## Database security findings

| Topic | Status |
|-------|--------|
| Schema `app` vs Data API | Must **not** be listed under Supabase “Exposed schemas” |
| `anon` / `authenticated` | No grants from our migrations; manual revoke script provided |
| RLS | **Not enabled yet** — required before any PostgREST exposure or multi-tenant HTTP reads |
| Least privilege | Documented: future `app_runtime` role; avoid long-term use of dashboard superuser in app |
| Public HTTP → private rows | Still blocked (Phase 2A: no private data routes; stub 401) |
| Trading via HTTP | Still disabled |

Manual script: `apps/api/sql/revoke_public_api_access.sql` (review before apply; not auto-run).

---

## Offline test results

```text
uv run pytest -q
128 passed
```

Includes URL redaction/SSL/pooler tests, migration audit, Alembic env bootstrap checks, API foundation tests, and Phase 1 suite.

Verified: `.env` and `data/*.sqlite3` remain gitignored.

---

## Manual Supabase connection instructions (approval required)

**Do not execute until the user explicitly approves a remote connection to a named development project.**

1. Confirm project ref + environment (dev only).
2. Set `DATABASE_URL` in local `.env` only (Session pooler or Direct + `sslmode=require`).
3. Read-only ping (prints **redacted** URL only):

```powershell
uv run python -c "from apps.api.app.config import get_api_settings; from apps.api.app.db import create_db_engine, ping_database; s=get_api_settings(); i=s.database_url_info(); print(i.redacted_url); print(i.pooler_hint, i.sslmode); ping_database(create_db_engine(s)); print('ping_ok')"
```

4. Review SQL plan (no apply):

```powershell
uv run alembic -c apps/api/alembic.ini upgrade head --sql
```

---

## Exact pending migration steps (manual)

After approval of the SQL plan:

```powershell
uv run alembic -c apps/api/alembic.ini upgrade head
```

Then verify in SQL editor:

- `app.agent_decisions`
- `app.system_events`
- `app.strategy_configs`
- `app.alembic_version` (revision `20261104_0001`)

Dashboard → API settings: ensure `app` is **not** exposed.  
Optional: apply `apps/api/sql/revoke_public_api_access.sql`.

**Do not** run `downgrade` automatically against shared databases.

---

## Remaining risks

1. Transaction pooler + long migrations can still fail (session/direct preferred).
2. Operator pasting unencoded passwords with `@` breaks URL parsing.
3. Without dashboard “Exposed schemas” discipline, PostgREST could still be pointed at `app` by mistake.
4. RLS not yet implemented — do not expose `app` via Data API.
5. Live connectivity and migrate were **not** executed in this phase.

---

## Next steps (authenticated read-only APIs)

1. AuthN (Supabase JWT or API keys) + AuthZ middleware.
2. Enable RLS with `env_scope` / tenant claims before any SELECT APIs.
3. Read-only routes for `system_events` / `agent_decisions` (still no trading).
4. Optional projection sync from SQLite SoT → Postgres (non-authoritative).
5. Wire `app_runtime` least-privilege role into server `DATABASE_URL`.

---

## Acceptance

| Criterion | Status |
|-----------|--------|
| Supabase connection config ready | Pass |
| Migration bootstrap validated offline | Pass |
| Application schema privacy plan documented | Pass |
| Offline tests pass | **128 passed** |
| No remote migrate / no Bybit / no trading HTTP | Pass |
