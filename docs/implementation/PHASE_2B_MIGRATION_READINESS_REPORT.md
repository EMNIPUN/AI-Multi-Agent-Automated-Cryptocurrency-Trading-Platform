# Phase 2B — Migration Readiness (Operator Review Gate)

| Field | Value |
|-------|-------|
| Date | 2026-11-04 |
| Project | CryptoNova — AI Multi-Agent Cryptocurrency Trading Platform |
| Goal | Finalize Phase 2B **readiness** without unapproved remote DDL |
| Remote migrate | **NOT executed** in this session |
| Exchange / trading | Not contacted / not enabled via HTTP |
| Execution SoT | Local SQLite (unchanged) |
| Offline suite | **129 passed** |

---

## Critical precondition (operator)

Credentials previously exposed in chat **must be rotated by the operator** before any further remote connection or migration.

- Rotate Bybit API key/secret and Supabase database password.
- Update local gitignored `.env` only.
- Never paste secrets into chat, reports, commits, or `NEXT_PUBLIC_*`.

This report contains **no** connection strings, passwords, or API keys.

---

## Migration review results

### `apps/api/alembic/env.py`

| Check | Result |
|-------|--------|
| Fresh schema bootstrap | `CREATE SCHEMA IF NOT EXISTS app` runs **before** version table / migrations (online + offline) |
| Version table | `app.alembic_version` (`version_table_schema=app`) |
| Scope filters | `include_name` / `include_object` limit to schema `app` |
| Autogenerate safety | Does not target `auth` / `storage` / `realtime` |
| Secrets in logs | Engine URL not printed |

### Revision `20261104_0001`

| Check | Result |
|-------|--------|
| Creates schema `app` | Yes (idempotent) |
| Tables | `app.agent_decisions`, `app.system_events`, `app.strategy_configs` |
| Indexes | See expected objects below |
| FKs outside `app` | None |
| `DROP SCHEMA … CASCADE` | Not present (downgrade drops tables only) |
| Observational only | Documented — not an execution/risk ledger |
| Model ↔ migration audit | `audit_initial_migration()` → **ok** |

### Generated offline SQL artifact

Path: `apps/api/sql/review/20261104_0001_upgrade_head.sql`  
Generated via Alembic offline workflow with a **localhost placeholder** URL (not Supabase credentials):

```powershell
$env:DATABASE_URL = "postgresql://review_only:unused@127.0.0.1:5432/postgres"
uv run alembic -c apps/api/alembic.ini upgrade head --sql
```

| SQL review check | Result |
|------------------|--------|
| `CREATE SCHEMA IF NOT EXISTS app` | Present (bootstrap + revision) |
| `CREATE TABLE app.alembic_version` | Present |
| App tables + indexes | Present |
| `INSERT … alembic_version … '20261104_0001'` | Present |
| Touches `auth` / `storage` / `realtime` | **No** |
| Secret-token leak scan | **Clean** |
| `scripts/audit_migration_sql_review.py` | `review_ok=True` |

---

## Expected SQL objects (after approved apply)

| Object | Type | Notes |
|--------|------|-------|
| `app` | schema | Application-only |
| `app.alembic_version` | table | Version `20261104_0001` |
| `app.agent_decisions` | table | PK `id`; JSONB `payload_json` |
| `ix_agent_decisions_env_created` | index | `(env_scope, created_at)` |
| `ix_agent_decisions_symbol_created` | index | `(symbol, created_at)` |
| `ix_agent_decisions_signal_id` | index | `(signal_id)` |
| `app.system_events` | table | PK `id`; JSONB `details_json` |
| `ix_system_events_env_created` | index | `(env_scope, created_at)` |
| `ix_system_events_type_created` | index | `(event_type, created_at)` |
| `app.strategy_configs` | table | PK `id`; JSONB `config_json` |
| `ix_strategy_configs_name` | **unique** index | `(name)` |

**Not created:** order intents, executions, risk ledgers (remain SQLite).

---

## Security and privilege review

### `apps/api/sql/revoke_public_api_access.sql`

| Aspect | Assessment |
|--------|------------|
| Purpose | Deny `PUBLIC` / Supabase `anon` / `authenticated` on schema `app` |
| Auto-run from FastAPI | **No** (manual only) |
| Impact on API roles | Blocks PostgREST access **if** `app` were exposed — defense in depth |
| Impact on migrator role | Dashboard/`postgres` (or your migrator login) retains ownership privileges |
| `ALTER DEFAULT PRIVILEGES` | Applies to future objects created by **current role**; re-run or set defaults for the owning role after role changes |
| RLS | **Not enabled** — do not expose `app` via Data API until RLS + auth exist |
| Least privilege (future) | Documented `app_runtime` role plan in script comments |

### Supabase Data API — verify `app` is not exposed

1. Open Supabase Dashboard → **Project Settings** → **API**.
2. Locate **Exposed schemas** (Data API / PostgREST).
3. Confirm the list does **not** include `app`.
4. Typical safe baseline: `public` (and only other schemas you intentionally publish).
5. Optionally call a PostgREST probe for a non-existent `app` table path and expect failure/404 — do not grant new access to test this.
6. After migration + optional revoke script, re-check Exposed schemas (migrations do not change this setting; humans can).

### Trading / private HTTP

- No new private-data endpoints added in this readiness pass.
- `AGENT_DRY_RUN` default **true**; `AGENT_ALLOW_LIVE` default **false** (unchanged in `agent/config.py` / `make_settings` offline defaults).

---

## Connection mode for migration (important)

| Mode | Port (typical) | Use for `alembic upgrade` |
|------|----------------|---------------------------|
| **Direct** | `5432` on `db.<ref>.supabase.co` | **Preferred** |
| **Session pooler** | `5432` on `*.pooler.supabase.com` | **Preferred** alternative |
| **Transaction pooler** | `6543` on pooler | **Avoid for migrations** (DDL / session features) |

Ping success on `:6543` does **not** mean migrate on `:6543`.  
Before apply, set local `DATABASE_URL` to Direct or Session (`5432`) + `sslmode=require`, then re-ping with redacted status only.

---

## Exact operator approval step

Reply explicitly in-band with something like:

> **APPROVED: apply Alembic `20261104_0001` to development Supabase project `<project-ref>` using Session/Direct (not 6543). Credentials rotated.**

Until that message exists, agents/operators must **not** run remote `upgrade head`.

---

## Manual deployment and verification (after approval only)

### A) Non-destructive pre-flight inspection (read-only)

In Supabase SQL editor (or `psql`) on the **dev** project:

```sql
-- Identity (no secrets)
SELECT current_database(), current_user, inet_server_addr();

-- Does app schema already exist?
SELECT nspname FROM pg_namespace WHERE nspname = 'app';

-- Any app tables already present?
SELECT table_schema, table_name
FROM information_schema.tables
WHERE table_schema = 'app'
ORDER BY 1, 2;

-- Alembic version present?
SELECT * FROM app.alembic_version;  -- may error if missing; that is OK pre-migrate
```

Stop if you are not on the intended **development** database.

### B) Review SQL locally again

```powershell
# Optional regenerate (localhost placeholder only)
$env:DATABASE_URL = "postgresql://review_only:unused@127.0.0.1:5432/postgres"
uv run alembic -c apps/api/alembic.ini upgrade head --sql
uv run python scripts/audit_migration_sql_review.py
```

Compare to `apps/api/sql/review/20261104_0001_upgrade_head.sql`.

### C) Apply (ONLY after explicit approval)

```powershell
# DATABASE_URL must be Direct or Session :5432 — set in local .env by operator
uv run alembic -c apps/api/alembic.ini current
uv run alembic -c apps/api/alembic.ini upgrade head
uv run alembic -c apps/api/alembic.ini current
```

### D) Post-apply verification

```sql
SELECT version_num FROM app.alembic_version;
SELECT table_name FROM information_schema.tables WHERE table_schema = 'app' ORDER BY 1;
SELECT indexname FROM pg_indexes WHERE schemaname = 'app' ORDER BY 1;
```

Expect tables: `alembic_version`, `agent_decisions`, `system_events`, `strategy_configs`.

### E) Optional privilege hardening

1. Confirm Exposed schemas excludes `app`.
2. Review then run `apps/api/sql/revoke_public_api_access.sql` on **dev** only.

### F) Application smoke (loopback)

```powershell
uv run uvicorn apps.api.main:app --host 127.0.0.1 --port 8000
```

Expect `[db] status=connected CONNECT_SUCCESS` (redacted). Still no trading routes.

---

## Rollback / recovery considerations

| Action | Guidance |
|--------|----------|
| `alembic downgrade -1` | Drops the three app tables + indexes; leaves schema `app` and may leave/empty version row depending on Alembic — **manual, approved only** |
| `DROP SCHEMA app CASCADE` | **Forbidden** in standard procedure — destroys version table and all app objects |
| Partial failure mid-upgrade | Inspect `app.alembic_version` and `\dt app.*`; restore from Supabase backup/PITR if available before re-attempt |
| Wrong project migrated | Treat as incident; do not “fix” with further DDL; use backup restore |
| SQLite trading ledgers | Unaffected by Postgres downgrade — still authoritative for execution/risk |

---

## Offline test / protection confirmation

| Check | Result |
|-------|--------|
| `uv run pytest -q` | **129 passed** |
| SQLite paths gitignored | `.env`, `data/*.sqlite3` ignored |
| `make_settings()` dry_run / allow_live | `True` / `False` |
| Migration SQL scope audit | `review_ok=True` |
| Remote `upgrade head` | **Not run** |

---

## Outstanding blockers

1. **Operator credential rotation** (mandatory precondition).
2. **Explicit written approval** to migrate the named **dev** project.
3. Switch `DATABASE_URL` to **Direct or Session `:5432`** before migrate (if still on transaction `:6543`).
4. Human confirmation that Supabase **Exposed schemas** exclude `app`.
5. Phase 2C still required before any authenticated private read APIs / RLS.

---

## Success criteria for this deliverable

| Criterion | Status |
|-----------|--------|
| Migration ready for explicit review | **Yes** |
| Offline SQL artifact available | **Yes** |
| No unapproved remote DDL | **Yes** |
| Offline tests green | **129 passed** |
| Trading protections unchanged | **Yes** |
