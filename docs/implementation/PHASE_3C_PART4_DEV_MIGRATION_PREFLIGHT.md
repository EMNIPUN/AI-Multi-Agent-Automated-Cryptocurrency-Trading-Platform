# Phase 3C Part 4 — Development Migration Preflight

| Field | Value |
|-------|-------|
| Date | 2026-11-06 |
| Target | **Isolated development / disposable DB only** |
| Migrations executed | **NO** (approval gate) |

---

## Offline migration chain (verified)

```text
None
  → 20261104_0001  (initial app schema)
  → 20261104_0002  (owner_user_id + catalog RLS)
  → 20261105_0003  (exchange_account_bindings)
```

| Check | Result |
|-------|--------|
| Single head | Yes |
| `down_revision` links | Correct |
| Offline `migration_audit` | Pass for 0001/0002/0003 |
| Conflicting heads | None |
| Models include bindings table | Yes |

---

## Planned schema changes on an **empty** development database

### After `0001`

- Schema `app`
- Tables: `agent_decisions`, `system_events`, `strategy_configs`, `app.alembic_version`

### After `0002`

- Nullable `owner_user_id` on catalog tables
- Owner indexes; per-owner unique strategy name
- RLS enabled + SELECT-own policies for role `authenticated` (when role exists)

### After `0003`

- `app.exchange_account_bindings` with checks, unique active indexes, RLS SELECT-own active rows
- No raw API keys in table (`credential_ref` opaque)

---

## Production comparison (do not migrate prod here)

| Item | Production (operator) | Development (planned) |
|------|----------------------|------------------------|
| Project | Known ref `wmirifmgaftassgrfbyl` | **Separate project — pending** |
| Revision | `20261104_0001` | Start empty → head `0003` |
| Bindings table | Absent | Created by `0003` |
| Gate B | INCOMPLETE | N/A (dev path) |

---

## Pre-execution checklist (operator)

Before **any** `alembic upgrade`:

1. [ ] Development project ref confirmed ≠ production  
2. [ ] `CRYPTONOVA_DB_TARGET=development`  
3. [ ] `CRYPTONOVA_DEV_PROJECT_REF` matches connection host/user  
4. [ ] `uv run python scripts/verify_dev_database_target.py --connect` → `DEV_TARGET_OK`  
5. [ ] Actual current revision on **dev** probed (expect empty or none)  
6. [ ] Unexpected objects/data on target → **STOP**  
7. [ ] Written approval recorded  
8. [ ] `CRYPTONOVA_ALLOW_DEV_MIGRATIONS=yes` set **only after** approval  
9. [ ] `uv run python scripts/verify_dev_database_target.py --require-migration-approval --connect`  

### Expected upgrade commands (after approval only)

```bash
# From repo root with DEV identity env loaded — DO NOT RUN until approved
uv run python scripts/verify_dev_database_target.py --require-migration-approval --connect
cd apps/api
# Ensure DATABASE_URL points at the verified DEV database
alembic upgrade 20261105_0003
alembic current
```

### Rollback considerations (dev only)

```bash
# Destructive to binding/ownership columns — confirmed disposable DB only
alembic downgrade 20261104_0001
# or full reset of a disposable project via Supabase dashboard
```

---

## Approval gate — STOP

**This document is not permission to migrate.**

Show the operator:

- Confirmed development project reference  
- Sanitized hostname (from guard summary)  
- Current Alembic revision on that database  
- Sequence `0001 → 0002 → 0003`  
- Confirmation target ≠ production  
- Rollback notes  

Then wait for explicit approval before executing upgrades.
