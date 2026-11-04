# apps/api — FastAPI (Phase 2A / 2B)

Read-only HTTP foundation + version-controlled PostgreSQL schema for Supabase.

## Safety

- Bound to `127.0.0.1` by default (`API_HOST`).
- No CORS wildcard.
- No create/cancel order, leverage, live-toggle, or emergency-reset routes.
- No private balances / positions / intents / risk over HTTP without auth (private stub → 401).
- Does **not** replace Phase 1 SQLite execution / risk ledgers.
- Does **not** auto-apply Alembic migrations to remote Supabase.
- Does **not** call Bybit.
- Schema `app` must stay **unexposed** in Supabase Data API settings.

## Run locally (no database required)

```powershell
uv sync --group dev
uv run uvicorn apps.api.main:app --host 127.0.0.1 --port 8000
```

- `GET /health` — liveness
- `GET /api/v1/system/status` — safe metadata
- `GET /api/v1/me` — Bearer Supabase user JWT (verified claims only)
- `GET /api/v1/agents/decisions|system/events|strategies` — auth required; **403** until ownership schema (`PRIVATE_DATA_READS_ENABLED`)

## DATABASE_URL (server-side only)

Set in local `.env` (gitignored). Never use `NEXT_PUBLIC_*`.

Supported shapes (psycopg3 normalized automatically):

- Direct: `postgresql://…@db.<project-ref>.supabase.co:5432/postgres?sslmode=require`
- Session pooler: host contains `pooler` and port **5432** (preferred for Alembic)
- Transaction pooler: port **6543** — fine for short queries; **prefer Session/Direct for migrations**

Passwords with special characters must be URL-encoded (or let the app re-encode userinfo).  
Remote hosts always get `sslmode=require` when `DATABASE_SSL_REQUIRE=true` (default).

## Migrations (manual only)

```powershell
# Review first
uv run alembic -c apps/api/alembic.ini history
uv run alembic -c apps/api/alembic.ini upgrade head --sql
```

Apply only after explicit approval:

```powershell
uv run alembic -c apps/api/alembic.ini upgrade head
```

Bootstrap: `env.py` runs `CREATE SCHEMA IF NOT EXISTS app` **before** `app.alembic_version` is created.

Optional privilege hardening (manual SQL review): `apps/api/sql/revoke_public_api_access.sql`

## Optional live development DB check (explicit approval required)

**Do not run these steps until the user explicitly approves a remote connection.**

1. Confirm the Supabase **project ref** and that this is a **development** database.
2. Put `DATABASE_URL` only in local `.env` (never commit; never paste into chat).
3. Prefer **Session pooler** or **Direct** for migrations; include `sslmode=require`.
4. Read-only ping (no DDL):

   ```powershell
   uv run python -c "from apps.api.app.config import get_api_settings; from apps.api.app.db import create_db_engine, ping_database; s=get_api_settings(); print(s.database_url_info().redacted_url); print(s.database_url_info().pooler_hint); ping_database(create_db_engine(s)); print('ping_ok')"
   ```

5. Review SQL plan offline:

   ```powershell
   uv run alembic -c apps/api/alembic.ini upgrade head --sql
   ```

6. Apply once:

   ```powershell
   uv run alembic -c apps/api/alembic.ini upgrade head
   ```

7. Verify (SQL editor or `psql`): tables `app.agent_decisions`, `app.system_events`, `app.strategy_configs`, and `app.alembic_version`.

8. Dashboard → Settings → API: ensure `app` is **not** an exposed schema. Optionally run `sql/revoke_public_api_access.sql`.

**Never** auto-run `downgrade` or destructive migrations against shared/prod projects from this app.
