# Phase 4D Option A — Final Least-Privilege Security Validation

| Field | Value |
| --- | --- |
| Prompt | 60 |
| Date | 2026-11-07 |
| Project | `wmirifmgaftassgrfbyl` |
| Decision | **READY FOR SEPARATE REMOTE CHANGE APPROVAL** |
| Supabase mutations | **NOT EXECUTED** |

---

## 1. Executive summary

Final validation of the Option A least-privilege package using:

- Read-only remote baseline confirmation (unchanged: `postgres` + BYPASSRLS).
- **Real local PostgreSQL 18** disposable cluster on `127.0.0.1:55432` (not the system service DB; not Supabase).
- Corrected proposed migration `20261108_0005` (still in `versions_proposed/` only).
- Offline mocks + full regression.

**18/18** disposable PostgreSQL role/RLS checks **PASSED**.  
Local `auth.uid()` was a **test stub** reading `request.jwt.claim.sub` — this is **not** live Supabase Auth E2E.

Remote apply remains unauthorized.

---

## 2. Current security baseline

| Item | Status | Class |
| --- | --- | --- |
| Project `wmirifmgaftassgrfbyl` | Confirmed in prior RO scripts | VERIFIED REMOTELY READ-ONLY |
| Alembic `20261107_0004` | Unchanged | VERIFIED REMOTELY READ-ONLY |
| Runtime role | `postgres`, `rolbypassrls=true` | VERIFIED REMOTELY READ-ONLY |
| Table owners | `postgres` | VERIFIED REMOTELY READ-ONLY |
| Existing policies | SELECT → `authenticated` only | VERIFIED REMOTELY READ-ONLY |
| Cloud writes / sync / orders | OFF | VERIFIED LOCALLY |
| Proposed revision location | `versions_proposed/` (inactive) | VERIFIED LOCALLY |

---

## 3. Proposed migration review

File: `apps/api/alembic/versions_proposed/20261108_0005_option_a_least_privilege.py`

| Check | Finding | Remediation in Prompt 60 |
| --- | --- | --- |
| Alembic dependency | `down_revision=20261107_0004` | OK |
| Schema | `app` only (+ `USAGE`/`EXECUTE` on `auth.uid`) | OK |
| Base role `NOINHERIT` | **Misleading** — LOGIN members default INHERIT and receive grants; NOINHERIT must be on LOGIN to block inheritance | Changed base to **INHERIT**; documented LOGIN must use INHERIT |
| LOGIN wrapper | Operator-created; must be `INHERIT IN ROLE cryptonova_api_runtime` | Documented + locally proven |
| Scheduler INSERT/UPDATE | Over-privileged for pre-Gate D | Deferred to **SELECT-only** |
| Duplicate catalog GRANT | Redundant | Removed |
| Policy idempotency | CREATE POLICY not idempotent | Wrapped in `pg_policies` existence check |
| DELETE for runtime | Not granted | Confirmed locally |
| Table ownership | Unchanged (must stay non-runtime) | Confirmed locally |
| Migrator | DML + `CREATE ON SCHEMA app`; no DROP ROLE in downgrade | Documented rollback limits |
| Supabase `auth.uid()` | Policies depend on it | GRANT EXECUTE added; live function not reimplemented remotely |

---

## 4. PostgreSQL role test results

**Environment:** disposable `initdb` cluster, user `cryptonova_test`, port **55432**, trust auth, host **127.0.0.1**.  
Harness: `scripts/_option_a_local_pg_rls_harness.py`  
Class: **VERIFIED LOCALLY WITH POSTGRESQL**

| Check | Result |
| --- | --- |
| Localhost-only bind | PASS |
| NOINHERIT LOGIN without SET ROLE → no table access | PASS |
| `cryptonova_api_runtime` not superuser | PASS |
| `rolbypassrls=false` | PASS |
| Base NOLOGIN | PASS |
| Base INHERIT | PASS |
| Runtime not table owner | PASS |
| LOGIN INHERIT member receives grants + RLS | PASS |

---

## 5. RLS test matrix

| Scenario | Result | Class |
| --- | --- | --- |
| Owner A reads A | PASS | VERIFIED LOCALLY WITH POSTGRESQL |
| Owner A cannot read B | PASS | VERIFIED LOCALLY WITH POSTGRESQL |
| Owner A insert own | PASS | VERIFIED LOCALLY WITH POSTGRESQL |
| Owner A insert as B | DENIED | VERIFIED LOCALLY WITH POSTGRESQL |
| Owner A update B | invisible / no effect | VERIFIED LOCALLY WITH POSTGRESQL |
| Missing `sub` → empty SELECT | PASS | VERIFIED LOCALLY WITH POSTGRESQL |
| Runtime DDL | DENIED | VERIFIED LOCALLY WITH POSTGRESQL |
| Runtime DELETE | DENIED | VERIFIED LOCALLY WITH POSTGRESQL |
| Sequential connection identity switch | PASS | VERIFIED LOCALLY WITH POSTGRESQL |
| Live Supabase Auth + RLS | — | **NOT VERIFIED** |
| Live Supabase `auth.uid()` under new role | — | **NOT VERIFIED** (post-apply gate) |

Stub note: local `auth.uid()` = `current_setting('request.jwt.claim.sub')::uuid`. Compatible with FastAPI GUC attach design; not a claim of Supabase Auth E2E.

---

## 6. JWT-to-database identity findings

Path remains:

JWT verify → principal `sub` → UUID validate → `set_config(..., true)` → `auth.uid()` → RLS.

Trust boundary unchanged: GUC is only safe with NOBYPASSRLS non-owner runtime credentials and no ad-hoc SQL. Helpers stay **disabled by default** (`RUNTIME_DB_IDENTITY_ENABLED=false`).

Pool/concurrency mocks: **VERIFIED WITH MOCKS** (Prompt 59). Sequential real connections: **VERIFIED LOCALLY WITH POSTGRESQL**.

---

## 7. Pool isolation findings

| Check | Result |
| --- | --- |
| ConnectionIdentityGuard checkout reset | VERIFIED WITH MOCKS |
| Concurrent IdentityLeakTracker | VERIFIED WITH MOCKS |
| Real sequential PG connections switch owner | VERIFIED LOCALLY WITH POSTGRESQL |
| SQLAlchemy NullPool vs QueuePool under GUC | Residual — use transaction-local SET LOCAL only; dispose pool on credential cutover |

---

## 8. Migrator privilege review

| Topic | Finding |
| --- | --- |
| Separate from FastAPI URL | Required |
| Proposed grants | SELECT/INSERT/UPDATE/DELETE on app tables + CREATE on schema `app` |
| Ownership | Should not become table owner casually — prefer ALTER by privileged migrator without REASSIGN to runtime |
| Alembic feasibility | Adequate for additive DDL; complex ownership changes need operator SQL |
| Downgrade | Revokes policies/grants; **does not DROP ROLE** |
| Rollback limit | Role/LOGIN password lifecycle is manual |

---

## 9. Phase 3C compatibility

Runtime receives **SELECT-only** on bindings/catalog with owner policies. Binding persistence flags remain OFF. No INSERT grant on bindings in revised migration.

---

## 10. Phase 4D compatibility

Signal write tables get SELECT/INSERT/UPDATE + owner policies for runtime. Scheduler write deferred. App-layer owner filters + dual write gates retained. SQLite SoT unchanged. Cloud sync still OFF.

---

## 11. Full regression results

| Suite | Result |
| --- | --- |
| Local PG harness | **18 passed** |
| Focused Option A + C1 + auth pytest | **38 passed** |
| Full `uv run pytest tests/` | **476 passed** (includes local PG harness when :55432 up) |
| Vitest | **32 passed** |
| `tsc --noEmit` | **exit 0** |

---

## 12. Local code changes (Prompt 60)

| Path | Change |
| --- | --- |
| `apps/api/alembic/versions_proposed/20261108_0005_option_a_least_privilege.py` | Corrected INHERIT, deferred scheduler writes, idempotent policies, auth EXECUTE, migrator CREATE |
| `scripts/_option_a_local_pg_rls_harness.py` | Disposable localhost RLS harness |
| `tests/test_option_a_least_privilege_security.py` | Invoke harness when `:55432` up |
| This report | Final validation evidence |

Not moved into active `alembic/versions/`.

---

## 13. Remaining risks

1. Live Supabase role creation / `GRANT EXECUTE ON auth.uid()` may need dashboard privileges.
2. Free-plan role limits unknown until apply attempt.
3. Credential cutover is a **separate** approval after DDL.
4. FORCE RLS not enabled — table owner still bypasses (runtime must not own tables).
5. Stub `auth.uid()` ≠ production Supabase function body (behavior aligned on GUC `sub`).

---

## 14. Exact remote-change scope (future approval)

1. Verify project `wmirifmgaftassgrfbyl`.
2. RO catalog snapshot.
3. Promote/apply `20261108_0005` only (or equivalent reviewed SQL).
4. Create LOGIN wrapper with INHERIT + password offline.
5. Expect: roles, grants, policies — **zero signal row changes**.
6. Verify `rolbypassrls=false` for runtime; policies present.
7. **Do not** switch FastAPI URL until separate cutover approval.
8. Keep cloud write/sync/order flags OFF.

---

## 15. Recovery and rollback plan

- Keep previous `DATABASE_URL` until cutover proven.
- Downgrade/revoke policies and grants per migration `downgrade()`.
- DROP LOGIN then base roles only after dependency audit.
- Alembic downgrade does **not** fully restore role secrets or LOGIN objects.
- Abort on wrong project, failed NOBYPASSRLS, or unexpected DML.

---

## 16. Final decision

### **READY FOR SEPARATE REMOTE CHANGE APPROVAL**

Rationale: migration design defects found in Prompt 59 draft were corrected and validated on real local PostgreSQL for role inheritance, RLS owner isolation, DELETE/DDL denial, and identity GUC behavior. Live Supabase apply and Auth E2E remain post-approval verification items, not blockers for requesting the remote security-change gate.

**READY ≠ authorized to apply.**
