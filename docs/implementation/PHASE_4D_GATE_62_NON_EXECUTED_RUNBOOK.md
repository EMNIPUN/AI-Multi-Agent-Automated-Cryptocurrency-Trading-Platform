# Phase 4D Gate 62 — Remote Security Migration Runbook (NON-EXECUTED)

| Field | Value |
| --- | --- |
| Status | **EXECUTED — see `PHASE_4D_GATE_62_EXECUTION_REPORT.md`** |
| Prerequisite | Gate 61 package + explicit Gate 62 operator approval |
| Project | `wmirifmgaftassgrfbyl` only |
| Revision | `20261108_0005` |
| Expected checksum | `9e0efdd317926a7ce5959f87e77c60c122e87ec62c49345597840cc6307f318a` |

Historical procedure text retained below. Live outcome: **MIGRATION_VERIFIED** on 2026-11-07 UTC.  
Companion execution evidence: `PHASE_4D_GATE_62_EXECUTION_REPORT.md`

---

## 1. Purpose

Apply Option A least-privilege **roles, grants, and RLS policies** to the development Supabase database. No signal data writes. No FastAPI credential cutover (Gate 63). No cloud sync / C2 / orders.

---

## 2. Preconditions checklist

- [ ] Gate 61 decision = GO
- [ ] Operator approval names project `wmirifmgaftassgrfbyl` and revision `20261108_0005`
- [ ] Checksum matches expected SHA-256
- [ ] Remote Alembic is still `20261107_0004`
- [ ] Phase 4D counts are 0
- [ ] `SIGNAL_SUPABASE_WRITES_*` / sync / import / order flags OFF
- [ ] `CRYPTONOVA_ALLOW_DEV_MIGRATIONS` remains false until the apply window
- [ ] Proposed file still describes INHERIT runtime/migrator; scheduler SELECT-only

---

## 3. Safety envelope

| Control | Required |
| --- | --- |
| Target | `wmirifmgaftassgrfbyl` / `ap-southeast-2` only |
| Connection | Existing privileged migration URL (same as Gate B) — **temporary** |
| Cloud writes | OFF |
| Sync worker | Not started |
| Exchange orders | OFF |
| Gate 63 | Not performed in this runbook |
| LOGIN password roles | Optional post-step; secrets never committed |

---

## 4. Proposed commands (AUTHORIZED GATE 62 ONLY)

### 4.1 Pre-change RO snapshot

```powershell
cd "E:\Financial Side\Trading\AI-Multi-Agent-Automated-Cryptocurrency-Trading-Platform"
uv run python scripts/_gate_c1_readonly_catalog.py
uv run python scripts/_option_a_readonly_rls_inventory.py
uv run python scripts/_gate_61_readonly_role_probe.py
Get-FileHash -Algorithm SHA256 apps\api\alembic\versions_proposed\20261108_0005_option_a_least_privilege.py
```

Abort if project/ref/revision/checksum mismatch or unexpected cryptonova roles already half-applied without matching policies.

### 4.2 Promote proposed revision into active Alembic path

```powershell
Copy-Item `
  apps\api\alembic\versions_proposed\20261108_0005_option_a_least_privilege.py `
  apps\api\alembic\versions\20261108_0005_option_a_least_privilege.py
Get-FileHash -Algorithm SHA256 apps\api\alembic\versions\20261108_0005_option_a_least_privilege.py
# Must equal 9e0efdd317926a7ce5959f87e77c60c122e87ec62c49345597840cc6307f318a
```

### 4.3 Apply migration (session-local allow flag)

```powershell
$env:CRYPTONOVA_DB_TARGET = "development"
$env:CRYPTONOVA_ALLOW_DEV_MIGRATIONS = "yes"
# Ensure DATABASE_URL still maps to wmirifmgaftassgrfbyl (do not print URL)
uv run python -m alembic -c apps/api/alembic.ini upgrade 20261108_0005
$upgradeExit = $LASTEXITCODE
$env:CRYPTONOVA_ALLOW_DEV_MIGRATIONS = "false"
Remove-Item Env:CRYPTONOVA_ALLOW_DEV_MIGRATIONS -ErrorAction SilentlyContinue
```

If `$upgradeExit -ne 0`: **halt**, do not cut over credentials, begin recovery (§7).

### 4.4 Immediate post-apply RO verification

```powershell
uv run python scripts/_gate_c1_readonly_catalog.py
uv run python scripts/_option_a_readonly_rls_inventory.py
uv run python scripts/_gate_61_readonly_role_probe.py
```

Expect:

- `remote_alembic` = `20261108_0005`
- `cryptonova_role_count` ≥ 2
- Phase 4D counts still 0
- New `*_runtime_*` policies listed
- Existing `authenticated` SELECT policies still present
- FastAPI env still using privileged URL (Gate 63 not done)
- All cloud/trading flags OFF

### 4.5 Optional LOGIN wrapper (still Gate 62 or deferred)

Only if approval includes creating LOGIN roles (passwords offline):

```sql
-- Run in Supabase SQL editor under project wmirifmgaftassgrfbyl ONLY
-- REPLACE password offline; never commit
CREATE ROLE cryptonova_api_runtime_login
  LOGIN PASSWORD '<offline-secret>'
  INHERIT
  IN ROLE cryptonova_api_runtime;
-- Do NOT point FastAPI at this role until Gate 63 approval
```

### 4.6 Offline regression after apply

```powershell
uv run pytest tests/test_option_a_least_privilege_security.py tests/test_phase4d_gate_c1_security.py -q
```

---

## 5. Abort conditions

Stop and disarm migration allow flag if:

- Project ref ≠ `wmirifmgaftassgrfbyl`
- Checksum mismatch
- Alembic was not `20261107_0004` before upgrade
- CREATE ROLE / GRANT / POLICY fails
- Any Phase 4D count becomes non-zero unexpectedly
- Cloud write/sync/order flags found enabled
- Upgrade appears partial (roles without policies or vice versa)

---

## 6. Explicit non-goals

Do **not** in Gate 62:

- Change FastAPI `DATABASE_URL` / enable `RUNTIME_DB_IDENTITY_ENABLED` (Gate 63)
- Enable `SIGNAL_SUPABASE_WRITES_*` or sync (Gate C2 / D)
- Historical import (Gate E)
- Exchange orders
- FORCE RLS / REASSIGN OWNED without separate approval
- Git push / deploy

---

## 7. Recovery sketch

1. Keep application on existing privileged connection (already the case).
2. If upgrade failed before version stamp: inspect objects; DROP POLICY / REVOKE as needed; leave roles until audited.
3. If version stamped but policies wrong: fix forward with approved SQL or carefully run `alembic downgrade 20261107_0004` knowing roles may remain.
4. Re-run RO probes; compare to Gate 61 baseline.
5. Do not invent signal data restores (counts should remain 0).

---

## 8. Evidence to capture in Gate 62 execution report

- Approval quote
- Pre/post catalog + role probe outputs (redacted)
- Checksums before/after promote
- Alembic before/after
- Confirmation flags OFF
- Statement: no credential cutover, no cloud writes, no orders

---

## 9. Non-execution attestation (Gate 61 / prep)

This runbook was prepared without:

- Promoting `20261108_0005` into active `versions/`
- Running `alembic upgrade`
- Creating remote roles/policies
- Changing runtime credentials
- Enabling cloud writes or placing exchange orders
