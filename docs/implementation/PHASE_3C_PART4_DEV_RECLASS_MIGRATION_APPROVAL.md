# Phase 3C Part 4 — Development reclassification & migration approval package

| Field | Value |
|-------|-------|
| Date | 2026-11-06 |
| Migrations executed | **YES — operator-approved 2026-11-06** (see `PHASE_3C_PART4_DEV_MIGRATION_EXECUTION_REPORT.md`) |
| Final revision | **`20261105_0003`** |
| New Supabase project | **Not created** (existing project reused) |

---

## 1. Verified development identity (read-only)

| Field | Value |
|-------|-------|
| Classification | **Development** (operator clarification: never designated production) |
| Project ref | `wmirifmgaftassgrfbyl` |
| Host | `aws-0-ap-southeast-2.pooler.supabase.com` |
| Port / pooler | `5432` / session_pooler |
| Database | `postgres` |
| Redacted URL | `postgresql+psycopg://postgres.wmirifmgaftassgrfbyl:***@aws-0-ap-southeast-2.pooler.supabase.com:5432/postgres?sslmode=require` |
| Current user | `postgres` (HAS_CREATE=true) |
| `authenticated` role | Exists |

Identity matches operator-stated project. Guard updated: this ref is in **approved-dev allowlist**; it is **no longer** on the production deny-list. Unknown/future production refs still fail closed via `CRYPTONOVA_PROD_PROJECT_REFS` + allowlist.

---

## 2. Preflight findings

| Check | Result |
|-------|--------|
| Alembic revision | **`20261104_0001`** (exact) |
| App tables | `agent_decisions`, `strategy_configs`, `system_events`, `alembic_version` |
| Row counts | **0 / 0 / 0** (empty catalog tables) |
| `exchange_account_bindings` | Missing (expected pre-`0003`) |
| `owner_user_id` columns | None (expected pre-`0002`) |
| RLS enabled | False on catalog tables |
| Policies | 0 |
| Migration chain | Linear `0001 → 0002 → 0003` |
| Destructive data overwrite risk | **Low** — tables empty; `0002` adds nullable columns + RLS; `0003` creates new table |
| Irreversible ops | Downgrade would drop policies/columns/table; **no auto-downgrade** planned |
| Verified backup | **None** |

### Backup note

No verified backup exists. With **zero rows** in application tables, risk of losing important *existing application data* is minimal. Schema-only recovery still benefits from a manual Supabase snapshot / `pg_dump` if available. Operator may proceed with awareness of that gap, or take a dashboard backup first.

---

## 3. Planned changes (not yet applied)

### Step A — `alembic upgrade 20261104_0002`

- Add nullable `owner_user_id` to `agent_decisions`, `system_events`, `strategy_configs`
- Replace global `ix_strategy_configs_name` with partial unique `(owner_user_id, name)` where owner not null
- ENABLE RLS + SELECT-own policies for role `authenticated`

### Step B — only if A succeeds — `alembic upgrade 20261105_0003`

- Create `app.exchange_account_bindings` + indexes + RLS SELECT-own active

**Do not** re-apply `0001`. **Do not** `stamp`. **Do not** auto-downgrade.

### Exact commands (after approval)

```powershell
# Identity (from repo root; load .env DATABASE_URL privately)
$env:CRYPTONOVA_DB_TARGET="development"
$env:CRYPTONOVA_DEV_PROJECT_REF="wmirifmgaftassgrfbyl"
$env:CRYPTONOVA_USE_DATABASE_URL_AS_DEV="true"
$env:CRYPTONOVA_ALLOW_DEV_MIGRATIONS="yes"   # ONLY after this approval
uv run python scripts/verify_dev_database_target.py --require-migration-approval --connect
uv run python scripts/probe_dev_database_readonly.py
cd apps/api
uv run alembic upgrade 20261104_0002
uv run alembic current
# verify then:
uv run alembic upgrade 20261105_0003
uv run alembic current
```

Expected final revision: **`20261105_0003`**.

---

## 4. Explicit operator confirmation required

Reply with approval to execute **only** if you confirm:

1. Target project `wmirifmgaftassgrfbyl` is the intended **development** database.  
2. You accept proceeding **without** a verified backup (empty tables noted).  
3. You authorize applying `20261104_0002` then `20261105_0003` on that database.  

Until that reply, **no migration will run**.

---

## 5. Post-migrate verification (after approval)

Synthetic JWT / binding isolation tests; RLS policy presence; final revision `20261105_0003`; keep `PRIVATE_DATA_READS_ENABLED=false`; no Bybit orders; no Git commit.
