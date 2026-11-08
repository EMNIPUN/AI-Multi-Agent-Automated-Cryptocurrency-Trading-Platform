# Phase 3C Part 4 — Development Migration Execution Report

| Field | Value |
|-------|-------|
| Date | 2026-11-06 |
| Target classification | **Development** (operator-approved) |
| Project ref | `wmirifmgaftassgrfbyl` |
| Host | `aws-0-ap-southeast-2.pooler.supabase.com` (session `:5432`) |
| Initial revision | `20261104_0001` |
| Final revision | **`20261105_0003`** |
| Private reads enabled | **No** |
| Bybit orders | **None** |
| Git commit/push | **None** |
| Downgrade/stamp | **Not used** |

---

## 1. Alembic identity guard (enforced in-process)

`apps/api/alembic/env.py` calls `_assert_dev_migration_target()` at the start of online and offline migration runs:

- `verify_dev_database_target(require_migration_approval=True)`
- Connection project-ref must match guard identity
- Hard-requires project ref `wmirifmgaftassgrfbyl`

**Proof (pre-execution):** `alembic current` without `CRYPTONOVA_ALLOW_DEV_MIGRATIONS=yes` failed with:

`alembic_dev_target_rejected:migrations_not_approved`

**During execution:** both upgrades logged  
`[alembic] identity_guard=ok classification=development project_ref=wmirifmgaftassgrfbyl host=aws-0-ap-southeast-2.pooler.supabase.com pooler=session_pooler`

---

## 2. Target confirmation before writes

| Check | Result |
|-------|--------|
| `DEV_TARGET_OK` + `--connect` | Pass |
| `IDENTITY_OK` | `wmirifmgaftassgrfbyl` |
| Pre-migrate revision | `20261104_0001` |
| Pre-migrate row counts | 0 / 0 / 0 |
| Bindings table | Missing |

---

## 3. Migration results

| Step | Command | Result |
|------|---------|--------|
| 1 | `alembic upgrade 20261104_0002` | **Success** (`0001 → 0002`) |
| 2 | `verify_migration_step.py 0002` | **VERIFY_0002_OK** |
| 3 | `alembic upgrade 20261105_0003` | **Success** (`0002 → 0003`) |
| 4 | `verify_migration_step.py 0003` | **VERIFY_0003_OK** |

### After `0002`

- `owner_user_id` on `agent_decisions`, `system_events`, `strategy_configs`
- RLS enabled on those tables
- Policies: `*_select_own` (3)
- `ix_strategy_configs_owner_name` present; global name unique index removed
- Row counts remained 0

### After `0003`

- Table `app.exchange_account_bindings` present
- RLS enabled; policy `exchange_account_bindings_select_own`
- Indexes include telemetry scope unique + active cred/env uniques
- Final `app.alembic_version` = **`20261105_0003`**
- All application table counts still **0** (data preserved / empty)

### Final policy set (4)

- `agent_decisions_select_own`
- `system_events_select_own`
- `strategy_configs_select_own`
- `exchange_account_bindings_select_own`

`authenticated` role exists. Table owner `postgres` bypasses RLS (expected); application JWT ownership tests remain primary for API isolation.

---

## 4. Ownership / security verification (synthetic)

| Suite | Result |
|-------|--------|
| Binding + Part2 + Part3 readiness + guard + auth + ownership | **92 passed** |

Covered offline/in-process: cross-user denial, service_role rejection, pending/revoked inactive, forged binding id, telemetry scope mismatch, credential allowlist, JWT rejection paths, env identity guard.

**Not enabled:** `PRIVATE_DATA_READS_ENABLED`, private SSE, live Bybit calls, Data API exposure change.

**Warning:** No verified backup existed before migrate; tables were empty so application row loss risk was minimal. Schema recovery still lacks a confirmed PITR/snapshot artifact.

---

## 5. Production Gate B distinction

Development DB is now at head **`20261105_0003`**.  
Production Gate B remains **INCOMPLETE** until backup/Data API evidences are recorded for whatever future production designation exists. This report does **not** mark production Gate B PASS.

---

## 6. Scoreboard

| Item | Result |
|------|--------|
| Verified project identity | `wmirifmgaftassgrfbyl` |
| Development classification | Confirmed |
| Alembic guard in env.py | Enforced |
| Initial revision | `20261104_0001` |
| Final revision | **`20261105_0003`** |
| Migration 0002 | Success + verified |
| Migration 0003 | Success + verified |
| Existing row preservation | 0→0 (empty preserved) |
| Isolation pytest subset | 92 passed |
| Private reads | false |
| Real Bybit orders | none |
| Git commit/push | none |
