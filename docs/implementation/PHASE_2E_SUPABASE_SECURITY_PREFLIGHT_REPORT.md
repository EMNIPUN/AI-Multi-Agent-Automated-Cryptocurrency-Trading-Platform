# Phase 2E — Supabase Security Preflight (Ownership / RLS `20261104_0002`)

| Field | Value |
|-------|-------|
| Date | 2026-11-04 |
| Project | CryptoNova |
| Mode | **Read-only** connectivity + offline code/SQL review |
| Alembic `upgrade` / `downgrade` / `stamp` | **Not executed** |
| Remote DDL/DML | **None** |
| `PRIVATE_DATA_READS_ENABLED` | **false** (unchanged; not flipped) |
| Bybit / trading HTTP | Not contacted / remain disabled |
| Secrets / full `DATABASE_URL` | Not printed |

Prior: `PHASE_2D_OWNERSHIP_ISOLATION_REPORT.md`, `PHASE_2C_AUTH_PROTECTED_READ_APIS_REPORT.md`, operator-applied `20261104_0001`.

---

## Recommendation

# READY

Technical preflight supports **explicit operator approval** to apply Alembic revision **`20261104_0002`** on this development project.

This report does **not** authorize `alembic upgrade`. Apply only after the operator procedure below. Keep **`PRIVATE_DATA_READS_ENABLED=false`** until post-apply verification succeeds.

---

## Redacted database identity

| Field | Observed |
|-------|----------|
| Configured | Yes |
| Redacted URL | `postgresql+psycopg://postgres.wmirifmgaftassgrfbyl:***@aws-0-ap-southeast-2.pooler.supabase.com:5432/postgres?sslmode=require` |
| Host | `aws-0-ap-southeast-2.pooler.supabase.com` |
| Port | **5432** |
| Database | `postgres` |
| Pooler hint | **session_pooler** |
| Project ref (username) | `wmirifmgaftassgrfbyl` — matches prior Phase 2B/2C development identity |
| `current_user` | `postgres` |
| Server version | PostgreSQL **17.11** |
| TLS (`sslmode`) | **require** |
| Connectivity | **CONNECT_SUCCESS** (SELECT-only inspection) |
| Intended CryptoNova **development** project | **Confirmed** (host + project-ref username; no password recorded) |

---

## Connection mode and TLS

| Check | Result |
|-------|--------|
| Direct / Session migrate-safe port | **Yes (`:5432`)** |
| Transaction pooler `:6543` | Not in use |
| Remote + TLS | **Yes** |
| Suitable for Alembic upgrade (when approved) | **Yes** |

---

## Current Alembic revision (read-only)

| Check | Result |
|-------|--------|
| Schema `app` | **Exists** |
| `app.alembic_version` | Present |
| Recorded revision | **`20261104_0001`** |
| Revision `20261104_0002` | **Pending (not applied)** |
| App base tables | `agent_decisions`, `system_events`, `strategy_configs` (+ `alembic_version`) |
| `owner_user_id` columns | **Absent** (expected pre-0002) |
| Row counts | All catalog tables **0** |
| Live state vs Phase 2D claim | Confirms 0002 has **not** been remotely applied |

---

## Existing catalog / RLS status (pre-0002)

| Table | RLS enabled | FORCE RLS | Policies |
|-------|-------------|-----------|----------|
| `app.agent_decisions` | **false** | false | none |
| `app.system_events` | **false** | false | none |
| `app.strategy_configs` | **false** | false | none |

| Privilege check | Result |
|-----------------|--------|
| Table grants to `anon` / `authenticated` / `PUBLIC` | **None observed** |
| Schema `app` ACL (`nspacl`) | `null` (no explicit broad grants visible) |
| Role `authenticated` | Exists; `rolbypassrls=false` |
| Role `anon` | Exists; `rolbypassrls=false` |
| Role `postgres` (API connection today) | **`rolbypassrls=true`** — RLS would not constrain this session |
| Role `service_role` | `rolbypassrls=true` (must never be used from browser) |

Indexes today include global unique `ix_strategy_configs_name` on `strategy_configs(name)` — replaced by per-owner unique in 0002.

---

## Expected migration changes (`20261104_0002`)

Source: `apps/api/alembic/versions/20261104_0002_ownership_rls.py`  
Review SQL: `apps/api/sql/review/20261104_0002_ownership_rls.sql`

| Change | Scope | Destructive to row data? |
|--------|-------|--------------------------|
| Add nullable `owner_user_id UUID` to 3 tables | `app` only | **No** — existing rows stay NULL |
| Indexes `(owner_user_id, created_at)` | `app` only | No |
| Drop `ix_strategy_configs_name`; create partial unique `(owner_user_id, name) WHERE owner_user_id IS NOT NULL` | `app` only | No row deletes; empty tables → no uniqueness conflict |
| `ENABLE ROW LEVEL SECURITY` on 3 tables | `app` only | No |
| `CREATE POLICY … FOR SELECT TO authenticated USING (owner_user_id IS NOT NULL AND owner_user_id = auth.uid())` | Conditional on role `authenticated` | No |
| `GRANT` to anon/authenticated | **None in revision** | N/A |
| Touch `auth` / `storage` / other schemas | **No** | N/A |

### Ownerless row behavior
- Existing / future `NULL owner_user_id` rows remain API-inaccessible via FastAPI equality filter.
- RLS policies also require `owner_user_id IS NOT NULL`.
- Migration does **not** invent owners.

### Downgrade risks (do **not** execute)
- Drops policies, disables RLS, drops `owner_user_id`, restores global unique name index.
- If owned rows later share the same `name` across users, downgrade unique restore can **fail**.
- Column drop loses ownership metadata — treat downgrade as emergency-only with backup/PITR.

---

## RLS and privilege findings

1. **RLS is defense in depth**, not the FastAPI isolation boundary while the API connects as `postgres` (`BYPASSRLS`).
2. Policies target **`authenticated` + `auth.uid()`** only — they do **not** grant access to `anon`.
3. Policies alone do not expose Data API access without schema USAGE + table grants + Exposed schemas.
4. Revision correctly avoids broad `GRANT USAGE ON SCHEMA app TO anon, authenticated`.
5. Manual revoke playbook remains: `apps/api/sql/revoke_public_api_access.sql` (not auto-run).
6. Least-privilege FastAPI role is **recommended, not applied**: `apps/api/sql/runtime_role_recommendations.sql` (`cryptonova_api_runtime`, SELECT-only, no `BYPASSRLS`). Until that role exists and `DATABASE_URL` uses it, **application `WHERE owner_user_id = :principal` remains mandatory and primary**.

---

## Operator dashboard exposure-check status

| Item | Status |
|------|--------|
| Verifiable via this SQL session | **No** (PostgREST “Exposed schemas” is Dashboard config) |
| Status | **REQUIRES_OPERATOR_DASHBOARD_CONFIRMATION** |
| Required action | Supabase Dashboard → Settings → API → Exposed schemas → ensure **`app` is not listed** |
| Blocks technical READY for migration apply? | **No** — remains a **required human checklist item before enabling private reads** |

---

## Authorization design review (code)

| Control | Status |
|---------|--------|
| Catalog SELECTs filter by verified `principal.user_id` → UUID | **Pass** (`catalog_service.py`) |
| JWT identity only (no client user-id headers) | **Pass** (Phase 2C verifier) |
| `PRIVATE_DATA_READS_ENABLED` default / current | **false** |
| Ownerless rows excluded | **Pass** (`== owner` excludes NULL) |
| JSON sanitization (`payload_json` / `details_json` / `config_json`) | **Pass** |
| Sensitive system event types filtered | **Pass** |
| `account_fp` omitted from response schemas | **Pass** |
| postgres/owner RLS bypass documented | **Pass** (2D report + migration docstring + this report) |
| Browser never receives DB owner credentials | **Pass** (server `.env` / no `NEXT_PUBLIC_` DB secrets in this phase) |
| Trading HTTP mutation routes | **Disabled** / absent on catalog |
| SQLite order/risk/fill SoT | **Unchanged** by this preflight |

---

## Offline test results

```text
uv run pytest -q
164 passed, 1 warning
```

Includes ownership isolation, JWT failures, schema/query fail-closed, migration SQL review, Phase 1A–1E and 2C regressions. Local/mock only — **does not prove production isolation**.

---

## Remaining security blockers (post-READY)

These do **not** block approving the migration itself, but **do** block enabling private catalog reads in a real environment:

1. Operator must **apply** `20261104_0002` (explicit approval).
2. Confirm Dashboard Exposed schemas exclude `app`.
3. Optionally apply revoke script if any accidental grants appear after other changes.
4. Prefer switching FastAPI to a **non-BYPASSRLS** SELECT role (recommendations SQL) before treating RLS as meaningful for the API connection.
5. Keep **`PRIVATE_DATA_READS_ENABLED=false`** until post-apply checks pass.
6. Do not invent owners for legacy NULL rows; define write-path ownership separately.

---

## Exact manual migration procedure (operator-only)

### Pre-apply checklist
1. Confirm this report’s redacted host/project-ref is the intended **development** project.
2. Confirm Session/Direct **`:5432`** + TLS (this preflight: OK).
3. Confirm `SELECT version_num FROM app.alembic_version;` → `20261104_0001`.
4. Review `apps/api/sql/review/20261104_0002_ownership_rls.sql`.
5. Confirm backup / PITR available.
6. Confirm Exposed schemas exclude `app` (Dashboard).

### Apply (only after explicit written approval)

```powershell
# From repo root; uses server-side DATABASE_URL (Session :5432).
# DO NOT run until operator approval is recorded.
uv run alembic -c apps/api/alembic.ini upgrade 20261104_0002
```

Do **not** run `downgrade`. Do **not** `stamp` without applying DDL.

### Post-apply verification (read-only SQL)

```sql
SELECT version_num FROM app.alembic_version;
-- expect: 20261104_0002

SELECT column_name, data_type, is_nullable
FROM information_schema.columns
WHERE table_schema = 'app' AND column_name = 'owner_user_id';

SELECT c.relname, c.relrowsecurity, c.relforcerowsecurity
FROM pg_class c
JOIN pg_namespace n ON n.oid = c.relnamespace
WHERE n.nspname = 'app'
  AND c.relname IN ('agent_decisions','system_events','strategy_configs');

SELECT tablename, policyname, roles, cmd, qual
FROM pg_policies
WHERE schemaname = 'app';

SELECT indexname, indexdef
FROM pg_indexes
WHERE schemaname = 'app' AND indexname LIKE '%owner%';
```

Expect: three nullable `owner_user_id` columns; RLS **enabled**; three `*_select_own` policies; owner indexes present; global `ix_strategy_configs_name` gone; partial unique `ix_strategy_configs_owner_name` present.

### After verification
1. Re-run `uv run pytest -q` (offline).
2. Leave **`PRIVATE_DATA_READS_ENABLED=false`** until a separate go/no-go for private reads.
3. Optional later: create least-privilege runtime role; point API `DATABASE_URL` at it; add matching RLS policies for that role if relying on RLS for the API session.

---

## Success checklist

| Criterion | Status |
|-----------|--------|
| Intended dev project confirmed (redacted) | Pass |
| Session `:5432` + TLS | Pass |
| `0001` applied / `0002` pending | Pass |
| Migration targets `app` only; non-destructive to rows | Pass |
| RLS/privilege design reviewed | Pass |
| Auth filters + sanitization reviewed | Pass |
| Dashboard Exposed schemas | **Operator confirmation required** |
| Offline tests | **164 passed** |
| No remote schema changes this phase | Pass |
| Ready for **operator-approved** `upgrade 20261104_0002` | **READY** |
