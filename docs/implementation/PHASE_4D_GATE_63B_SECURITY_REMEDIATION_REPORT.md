# Phase 4D Gate 63B — Security Remediation Report

| Field | Value |
| --- | --- |
| Gate | **63B — LOCAL REMEDIATION** |
| Date | 2026-11-08 |
| Decision | **READY FOR SEPARATE REMOTE GRANT AUTHORIZATION REVIEW** |
| Project | `wmirifmgaftassgrfbyl` |
| Alembic | `20261108_0005` |
| Remote mutations | **None** |
| Credential cutover | **NOT EXECUTED** |

Companions:

- `PHASE_4D_GATE_63B_AUTH_SCHEMA_GRANT_PROPOSAL.md`
- `PHASE_4D_GATE_63_NON_EXECUTED_CUTOVER_RUNBOOK.md` (updated)
- `PHASE_4D_GATE_63A_RUNTIME_CUTOVER_PREFLIGHT.md`

---

## 1. Current security baseline

| Item | Observed |
| --- | --- |
| Project / region | `wmirifmgaftassgrfbyl` / `ap-southeast-2` |
| PostgreSQL (remote) | **17.11** |
| Alembic | `20261108_0005` |
| Roles | `cryptonova_api_runtime`, `cryptonova_migrator` (NOLOGIN, NOBYPASSRLS, INHERIT) |
| LOGIN `cryptonova_api_login` | absent |
| FastAPI connection | privileged `postgres` (BYPASSRLS) |
| Flags | identity OFF; writes/sync/import/orders OFF; `AGENT_ALLOW_LIVE=false` |

---

## 2. Exact blockers (from 63A) and status

| Blocker | Status after 63B |
| --- | --- |
| A — missing effective `USAGE ON SCHEMA auth` | **Root cause proven**; remote grant **proposed, not executed** |
| B — `DATABASE_RUNTIME_URL` unused / no fail-closed selection | **Implemented locally**, default OFF |
| Pool isolation gap | **Closed** on disposable local PG 18.6 |

---

## 3. Root-cause findings (auth USAGE)

1. Schema `auth` owned by `supabase_admin`.
2. ACL grants USAGE to anon/authenticated/service_role/postgres/admins — **not** `cryptonova_api_runtime`.
3. `postgres` has USAGE with **`is_grantable=false`** → cannot GRANT to runtime.
4. Gate 62 `GRANT USAGE` therefore did not stick.
5. `EXECUTE` on `auth.uid()` is true (PUBLIC + runtime grant).
6. Local disposable PG: **direct** `SELECT auth.uid()` fails without USAGE; RLS policy SELECT still succeeded without USAGE on PG **18.6** (document residual). Grant USAGE anyway for portable least-privilege and diagnostics.

Authorized future grantor: principal with GRANT OPTION on `auth` (Supabase SQL / `supabase_admin`), **not** ordinary `postgres` session alone.

---

## 4. Local code changes

| File | Change |
| --- | --- |
| `apps/api/app/runtime_db.py` | **NEW** — resolve URL, reject privileged usernames, probe/assert NOBYPASSRLS |
| `apps/api/app/config.py` | `sqlalchemy_url()` → runtime-aware; `sqlalchemy_url_legacy()` for admin |
| `apps/api/app/db.py` | `configure_engine` validates identity only when flag ON |
| `apps/api/alembic/env.py` | Alembic uses **legacy** URL only |
| `scripts/_gate_63b_*` | RO probe + local auth USAGE harness |
| `tests/test_gate_63b_runtime_db_fail_closed.py` | **NEW** fail-closed unit tests |
| `scripts/_option_a_local_pg_rls_harness.py` | Drop sibling DB before role recreate |
| `.gitignore` | `.local_pg_63b/` |

Active `.env` secrets and flags: **unchanged**.

---

## 5. Remote grant analysis

See `PHASE_4D_GATE_63B_AUTH_SCHEMA_GRANT_PROPOSAL.md`.

Minimum SQL:

```sql
-- NON-EXECUTED — SEPARATE OPERATOR APPROVAL REQUIRED
GRANT USAGE ON SCHEMA auth TO cryptonova_api_runtime;
```

---

## 6. Fail-closed startup behavior

| Mode | Behavior |
| --- | --- |
| `RUNTIME_DB_IDENTITY_ENABLED=false` (default) | `DATABASE_URL` only — **unchanged** |
| `=true` (future) | Require `DATABASE_RUNTIME_URL`; reject empty; reject privileged usernames (`postgres`, `service_role`, …); **no fallback** to `DATABASE_URL`; optional live probe refuses `rolbypassrls` / superuser |

Username checks are heuristic; live `session_user` + `rolbypassrls` probe is mandatory at Gate 63 startup.

---

## 7. Local PostgreSQL results

| Item | Value |
| --- | --- |
| Cluster | disposable `127.0.0.1:55432` |
| Version | **PostgreSQL 18.6** (17 unavailable; semantics compatible) |
| Harness | `_gate_63b_local_auth_usage_harness.py` → **19/19 PASS** |
| Owner isolation | PASS |
| DELETE/DDL deny | PASS |
| Pool reuse clears SET LOCAL | PASS |
| LOGIN inherit | PASS |

---

## 8. Connection-pool isolation

| Test | Result |
| --- | --- |
| Real QueuePool size=1, A→rollback→B | PASS (no GUC leak) |
| Unit `ConnectionIdentityGuard` | PASS |
| Concurrent IdentityLeakTracker | PASS |

---

## 9. JWT identity verification

Existing JWKS verifier + `attach_owner_identity` unchanged and still disabled by default. Cloud router attaches GUC only when flag ON. Tests covering JWT wiring / Option A identity: included in 63B suite (**38 passed** for selected files).

---

## 10. Rollback readiness

Documented in Gate 63 runbook: restoring privileged `DATABASE_URL` after a live cutover is a **security regression** requiring separate approval. Identity flag stays OFF until authorized cutover.

---

## 11. Residual risks

1. Remote auth USAGE still missing until authorized grant.
2. Policy-vs-direct `auth.uid()` behavioral nuance on PG18 without USAGE.
3. Live Supabase Auth isolation not executed (Gate 63).
4. System PG17 disposable instance not available this session (used 18.6).
5. Engine still privileged in active runtime.

---

## 12. Safety flags

| Flag | State |
| --- | --- |
| RUNTIME_DB_IDENTITY_ENABLED | OFF |
| Cloud writes / sync / import | OFF |
| AGENT_ALLOW_LIVE | false |
| Orders | OFF |
| CRYPTONOVA_ALLOW_DEV_MIGRATIONS | false |

---

## 13. Acceptance criteria

| Criterion | Result |
| --- | --- |
| Correct project | **PASS** |
| Correct Alembic | **PASS** |
| Gate 62 roles intact | **PASS** |
| Auth USAGE requirement established | **PASS** |
| Minimum remediation documented | **PASS** |
| Fail-closed engine implementation | **PASS** |
| No privileged fallback | **PASS** |
| Runtime LOGIN inheritance design | **PASS** |
| PostgreSQL 17 local tests | **CONDITIONAL** (ran on **18.6**) |
| Owner-scoped RLS | **PASS** (local) |
| SQLAlchemy pool isolation | **PASS** |
| JWT identity binding | **PASS** (disabled) |
| Credential management readiness | **PASS** (design) |
| Rollback readiness | **PASS** |
| Safety flags | **PASS** |
| No remote mutations | **PASS** |

---

## 14. Final decision

### **READY FOR SEPARATE REMOTE GRANT AUTHORIZATION REVIEW**

Not authorization to GRANT, create LOGIN, or cut over credentials.

Next: operator-approved auth USAGE grant (proposal doc) → then separate Gate 63 LOGIN + cutover authorization.

---

## 15. Non-execution attestation

No remote DDL/DML, GRANT/REVOKE, role creation, Alembic change, credential rotation, identity enablement, cloud writes, sync, import, exchange orders, deployment, or git push.
