# Phase 3C Part 4 — Gate B: Database Migration Preflight Report

| Field | Value |
|-------|-------|
| Date | 2026-11-06 |
| Updated | 2026-11-06 (operator remote revision evidence) |
| Gate | **B only** (no upgrade/downgrade/stamp/DDL/DML) |
| Verdict | **INCOMPLETE** |

---

## Why incomplete (STOP before Gate C)

1. **Usable backup / PITR** not independently confirmed.  
2. **Schema / RLS verification** for ownership (`0002`) and bindings (`0003`) not yet evidenced on the remote DB (expected absent until Gate C).  
3. **Supabase Data API exposure** of schema `app` not independently confirmed as excluded.  

Remote Alembic revision is **no longer unknown** (see B3). Per runbook: do not apply migrations until remaining Gate B checks pass and Gate C is explicitly approved.

**This update does not apply migrations and does not flip private-read / SSE / trading flags.**

---

## B1 — Migration configuration (offline)

| Item | Evidence |
|------|----------|
| `alembic.ini` `script_location` | `apps/api/alembic` |
| Placeholder URL in ini | `driver://user:pass@localhost/dbname` (not used at runtime) |
| Runtime URL source | `alembic/env.py` → `get_api_settings().sqlalchemy_url()` from `DATABASE_URL` |
| Version table | `app.alembic_version` (`version_table_schema=app`) |
| Schema bootstrap | `CREATE SCHEMA IF NOT EXISTS app` before version table |
| Autogenerate scope | Limited to schema `app` |

### Revision chain (single head)

```text
None → 20261104_0001 → 20261104_0002 → 20261105_0003
```

No conflicting heads observed in `apps/api/alembic/versions/`.

Offline audits (`migration_audit`):

| Revision | File verified | Offline audit |
|----------|---------------|---------------|
| `20261104_0001` | Yes | **Pass** (`ok=True`, issues=[]) |
| `20261104_0002` | Yes | **Pass** |
| `20261105_0003` | Yes (untracked until commit) | **Pass** |

Model tables seen by audit: `app.agent_decisions`, `app.system_events`, `app.strategy_configs`, `app.exchange_account_bindings`.

---

## B2 — Migration safety review (files only)

### `0001` — initial app schema

- Creates schema `app` + observational tables (not order/risk authority).
- Downgrade drops tables; risk if data present after apply.
- No CASCADE schema drop in upgrade path (audit enforced).

### `0002` — ownership RLS

- Adds nullable `owner_user_id` (legacy rows unowned / inaccessible via policy).
- Enables RLS + SELECT-own policies for role `authenticated` when role exists.
- Does **not** GRANT schema USAGE to anon/authenticated.
- Application filters remain primary; table owner may bypass RLS.

### `0003` — `app.exchange_account_bindings`

- Opaque `credential_ref`; no raw API keys.
- Checks: provider=`bybit`; env in testnet/mainnet/demo; status pending/active/revoked/error.
- Unique active `(provider, credential_ref)` and `(owner_user_id, provider, environment)`.
- Unique `telemetry_scope_id`.
- RLS: SELECT own **active** rows for `authenticated`; no INSERT/UPDATE/DELETE policies for that role.
- Enrollment remains operator-attested (application layer).

### Data-loss / compatibility notes

- Applying `0002` on populated catalog tables: nullable columns OK; name uniqueness becomes per-owner.
- Applying `0003`: new table only — low conflict if `0002` already applied.
- Downgrade `0003` drops bindings table (data loss). Downgrade past `0002` drops ownership columns/indexes.
- **Never stamp** without applying if schema is empty/drifted.

Review artifacts: `apps/api/sql/review/20261104_0002_*.sql`, `.../20261105_0003_*.sql`, `runtime_role_recommendations.sql`.

---

## B3 — Database connectivity / remote revision evidence

### Operator-verified production probe (2026-11-06)

| Check | Result |
|-------|--------|
| Method | Supabase **SQL Editor** + **Table Editor** (operator-independent verification) |
| Schema | `app` |
| Version table | `app.alembic_version` |
| **Current revision** | **`20261104_0001`** |
| Tables visible (Table Editor) | `agent_decisions`, `strategy_configs`, `system_events` |
| `exchange_account_bindings` | **Not reported present** (consistent with `0003` not applied) |
| `owner_user_id` / RLS from `0002` | **Not yet verified** on remote (expected incomplete until Gate C) |
| Agent `DATABASE_URL` / `alembic current` | Not used for this evidence path; no upgrade/stamp run |

This resolves the prior “revision unknown because file exists” gap: **`0001` is applied on production**. Head remains behind local chain (`0002`, `0003` prepared only).

### Remaining read-only checks (still required for Gate B PASS)

1. Confirm Supabase PITR / snapshot backup usable.  
2. Verify RLS / column state for catalog tables (document whether `owner_user_id` exists — should be absent pre-`0002`).  
3. Confirm schema `app` is **not** in Supabase Data API exposed schemas.  
4. Optionally re-check `SELECT version_num FROM app.alembic_version;` immediately before Gate C.  
5. Written Gate C approval only after Gate B → PASS.

---

## B4 — Backup readiness

| Check | Result |
|-------|--------|
| Live PITR/snapshot confirmation | **Unverified** |
| Restore drill documented in-repo | Runbook references only |
| Operator-confirmed usable backup | **Not evidenced in this session** |

**Gate B incomplete until backup is explicitly confirmed by the operator.**

---

## B5 — Migration readiness verdict

| Migration | File | Offline audit | Remote applied | Safe for operator Gate C consideration |
|-----------|------|---------------|----------------|----------------------------------------|
| `20261104_0001` | Verified | Pass | **Yes** (`app.alembic_version` = `20261104_0001`) | Baseline confirmed |
| `20261104_0002` | Verified | Pass | **No** (not applied) | Blocked until backup + RLS/Data API checks |
| `20261105_0003` | Verified | Pass | **No** (not applied; bindings table not reported) | Blocked until `0002` applied under Gate C |

**Migrations applied by this update / gate session: None.** Next upgrade path after Gate B PASS + Gate C approval: `0001` → `0002` → `0003`.

---

## Security dependencies (reviewed, not activated)

- Private reads default **false**; SSE default **false**; wallet reads flag true but ownership-gated — **unchanged**.
- Binding store + allowlisted credential resolver present in code; no auto-enrollment performed.
- Local break-glass in ignored `.env.local` only — keep off shared hosts.
- No authenticated Bybit calls; no RLS/grant changes executed.

---

## Gate B verdict: **INCOMPLETE**

### Required before recommending Gate C

- [x] Remote revision recorded (`20261104_0001` via SQL/Table Editor)  
- [x] Initial `app` tables visible (`agent_decisions`, `strategy_configs`, `system_events`)  
- [ ] Operator confirms usable backup / PITR  
- [ ] Schema / RLS verification for pre-`0002` state documented  
- [ ] Confirm `app` not exposed on Data API  
- [ ] Written approval for Gate C only after Gate B → PASS  

**STOP:** Do not run `alembic upgrade` until Gate B is completed to PASS by the operator with evidence.

---

## Development path vs production Gate B (Part 4 clarification)

Isolated **development** Supabase setup and migration rehearsal are documented under:

- `PHASE_3C_PART4_DEV_ENV_SETUP.md`
- `PHASE_3C_PART4_DEV_MIGRATION_PREFLIGHT.md`
- `PHASE_3C_PART4_DEV_MIGRATION_TEST_PLAN.md`
- `scripts/verify_dev_database_target.py`

**A successful development migration does not mark this production Gate B as PASS.**  
Production remains blocked on backup/PITR, schema/RLS verification, Data API exposure confirmation, and separate Gate C approval.
