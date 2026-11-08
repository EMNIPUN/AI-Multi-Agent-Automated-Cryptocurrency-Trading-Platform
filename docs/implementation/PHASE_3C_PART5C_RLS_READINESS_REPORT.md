# Phase 3C Part 5C — Auth Verification & RLS Test Readiness

| Field | Value |
|-------|-------|
| Date | 2026-11-06 |
| Development project | `wmirifmgaftassgrfbyl` |
| Alembic | `20261105_0003` |
| Real RLS `--execute` | **NOT RUN** |
| Git commit/push | **None** |

---

## Task 1 — Next.js Supabase configuration

| Check | Result |
|-------|--------|
| `NEXT_PUBLIC_SUPABASE_URL` | Matches `https://wmirifmgaftassgrfbyl.supabase.co` |
| Publishable key present | **Yes** (`sb_publishable_…` shape; value not logged) |
| Env file location | Operator key found in `apps/web/.env`; synced to `apps/web/.env.local` (both gitignored) |
| `@supabase/supabase-js` installed | **2.119.0** (publishable-key capable) |
| `package.json` range | Updated to `^2.119.0` |
| Service-role exposed in web env | **No** |
| Break-glass | **`OPERATOR_LOCAL_BROWSER_PROXY_ENABLED=false`** |
| Session path | Supabase client when configured; no sessionStorage substitute |
| Sync header helper | Hardened: returns `{}` when public Supabase env set |

**Verdict:** Next.js config **PASS** for publishable-key compatibility. Restart `npm run dev` so Next picks up `.env.local`.

---

## Task 2 — API Auth configuration

| Check | Result |
|-------|--------|
| `SUPABASE_URL` | Development project host |
| `AUTH_JWT_MODE` | `jwks` |
| Audience | `authenticated` |
| JWKS | ES256 key reachable (Part 5) |
| Wrong-project issuer | Rejected (offline) |
| Service-role as user | Rejected (offline) |
| `PRIVATE_DATA_READS_ENABLED` | **false** |

**Verdict:** API JWT configuration **PASS**.

---

## Task 3 — Data API

| Check | Result |
|-------|--------|
| Saved-and-refreshed evidence on file | **Missing** |
| `app` exposure | **PENDING** |
| Agent-changed settings | **No** |

**STOP for `--execute`:** require operator reply `DATA_API_VERIFIED: app not exposed` after refreshed Dashboard confirmation (exposed schemas exclude `app`; automatic new-table exposure disabled).

---

## Task 4 — Transactional RLS plan validation

Live catalog checks against PostgreSQL 17.11 / revision `20261105_0003`:

| Item | Result |
|------|--------|
| Planned UUIDs | Valid |
| Binding CHECKs / unique indexes | Compatible with planned rows |
| `postgres` ∈ `authenticated` | **Yes** (SET ROLE feasible) |
| **FINDING fixed** | `agent_decisions.strategy_id` is NOT NULL without DB default — INSERT now supplies `''` |
| Assertions | Hard `_assert_eq` failures (not print-only) |
| `auth.uid()` check | Explicit equality to synthetic UUID |
| Privileged-only proof | Forbidden — probe uses `SET LOCAL ROLE authenticated` |
| Rollback | Unconditional; independent post-verify connection |

Docs updated: `PHASE_3C_PART5B_TRANSACTIONAL_RLS_EXECUTION_PLAN.md`.

---

## Task 5 — Runner safeguards

Script: `scripts/run_transactional_rls_isolation.py`

| Safeguard | Behavior |
|-----------|----------|
| Default mode | **Dry-run** (read-only) |
| Identity guard | `verify_dev_database_target` → must be `wmirifmgaftassgrfbyl` |
| Revision | Must be `20261105_0003` |
| `--execute` gates | `CRYPTONOVA_APPROVE_TRANSACTIONAL_RLS=yes` **and** `CRYPTONOVA_DATA_API_APP_NOT_EXPOSED=yes` |
| Commit | Never |
| Secrets in logs | Not printed |
| Migrations | Not invoked |

Dry-run was executed successfully in Part 5C. **`--execute` was not run.**

---

## Task 6 — Offline tests

| Suite | Count |
|-------|-------|
| Python security-related | **117 passed** |
| Frontend vitest | **15 passed** |
| RLS runner dry-run | **OK** (`RLS_PROBE_DRY_RUN_OK`; no writes) |

---

## Final scoreboard

| Check | Result |
|-------|--------|
| Development identity | **Verified** |
| Next.js Supabase configuration | **PASS** |
| Publishable key compatibility | **PASS** |
| API JWT configuration | **PASS** |
| Data API `app` exposure | **Pending** |
| Transactional RLS test script | **Ready** (dry-run OK; execute gated) |
| Synthetic INSERT constraints | **Verified** (strategy_id fix applied) |
| Rollback safeguards | **PASS** (design + dry-run gates) |
| Real database RLS test | **NOT EXECUTED** |
| Python tests | **117** |
| Frontend tests | **15** |
| Database writes | **NONE** |
| Private wallet reads | **DISABLED** |
| Live trading | **DISABLED** |
| Git commit/push | **NONE** |

---

## Operator approval request (STOP)

Before any `--execute` run, reply with **both**:

1. `DATA_API_VERIFIED: app not exposed` (refreshed Dashboard; auto-expose off)
2. `APPROVE_TRANSACTIONAL_RLS_PART5B`

This prompt is **not** write approval.
