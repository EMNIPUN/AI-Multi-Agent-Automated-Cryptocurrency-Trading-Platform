# Phase 3C Part 5B — Security Gate Status

| Field | Value |
|-------|-------|
| Date | 2026-11-06 |
| Full security gate | **NOT PASS** |
| Part 5B scope | Auth wiring prep, Data API checklist, transactional RLS plan, privileged-role architecture |

---

## Final scoreboard

| Item | Result |
|------|--------|
| Development database identity | **Verified** (`wmirifmgaftassgrfbyl`) |
| Alembic revision | **`20261105_0003`** |
| Data API `app` exposure | **Pending** (operator checklist) |
| API Auth environment | **Ready** |
| Next.js Auth environment | **Pending** (anon key missing) |
| Operator break-glass | **Disabled** |
| RLS transactional test design | **Ready** (awaiting approval) |
| Actual database RLS tests | **NOT EXECUTED** |
| Privileged DB connection risk | **Documented** (below) |
| Python tests | **117 passed** |
| Frontend tests | **15 passed** |
| Database writes | **NONE** |
| Migrations | **NONE** |
| Private wallet reads | **DISABLED** |
| Live trading | **DISABLED** |
| Git commit/push | **NONE** |

---

## Privileged connection architecture (Task D)

### Current state

| Fact | Detail |
|------|--------|
| SQLAlchemy URL user | Supabase `postgres` (pooler user `postgres.<ref>`) |
| `rolbypassrls` | **true** |
| FORCE RLS | **false** on all four app tables |
| SET ROLE / JWT GUCs in API | **Not used** (`deps.get_db_session` intentionally avoids them) |

Therefore **every** FastAPI SQL query against `app.*` **bypasses RLS**.

### Application compensations (primary isolation)

| Surface | Filter / gate |
|---------|----------------|
| Catalog lists | `owner_user_id == principal.user_id` in `catalog_service.py` |
| Catalog access | `require_private_catalog_access` → JWT + `PRIVATE_DATA_READS_ENABLED` |
| Wallet / telemetry | `require_active_binding_for_principal` (owner, status, env, binding id) |
| Telemetry scope | `assert_telemetry_scope_access` after binding authz |
| Kill switch | `PRIVATE_DATA_READS_ENABLED=false` → fail closed |

### Store methods that query without owner predicate

These still run as `postgres` (RLS bypass). Safety depends on **callers**:

| Method | SQL filter | Caller protection |
|--------|------------|-------------------|
| `SqlAlchemyBindingStore.get(id)` | by primary key only | Ownership compared after load in `require_active_binding_for_principal` |
| `find_by_telemetry_scope` | by scope id only | Used after owner-bound binding resolution / scope assert |
| `find_active_by_credential_ref` | provider+ref+active | Enrollment uniqueness — not an end-user read API |

No catalog list path was found that omits the owner `WHERE` clause.

**Residual risk:** any future route that calls `get` / scope lookup and returns data **without** the ownership assert would leak under BYPASSRLS. Code review + tests remain mandatory until a non-bypass role is adopted.

### Least-privilege feasibility (future, separately approved)

Recommended direction (already sketched in `apps/api/sql/runtime_role_recommendations.sql`):

1. Create login role e.g. `cryptonova_api_runtime` **without** `BYPASSRLS` / superuser.
2. `GRANT USAGE ON SCHEMA app` + least table privileges needed.
3. Add RLS policies `TO cryptonova_api_runtime` **or** `SET ROLE` + `request.jwt.claim.sub` per request (pool-safe design required).
4. Keep migrations on elevated role only.
5. Point `DATABASE_URL` at the runtime role.

Until then: **do not claim database-enforced isolation for the API path.**

---

## Blockers to full gate PASS

1. Operator Data API evidence (`app` not exposed).
2. Operator sets `NEXT_PUBLIC_SUPABASE_ANON_KEY` in `apps/web/.env.local`.
3. Explicit approval + successful execution of transactional RLS plan.
4. (Later, separate) Class D Auth E2E; least-privilege DB role; Gate F private reads.

---

## Documents

| Doc | Role |
|-----|------|
| `PHASE_3C_PART5B_AUTH_CONFIGURATION_REPORT.md` | Auth wiring |
| `PHASE_3C_PART5B_DATA_API_VERIFICATION.md` | Dashboard checklist |
| `PHASE_3C_PART5B_TRANSACTIONAL_RLS_EXECUTION_PLAN.md` | Approval-gated Class C SQL |
| `PHASE_3C_PART5_RLS_TEST_PLAN.md` | Updated pointer to transactional design |
| `PHASE_3C_PART5B_SECURITY_GATE_STATUS.md` | This status |
