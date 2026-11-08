# Phase 4D Gate 63 — Runtime Credential Cutover Runbook (NON-EXECUTED)

```
╔══════════════════════════════════════════════════════════════╗
║  NON-EXECUTED — REQUIRES SEPARATE EXPLICIT AUTHORIZATION     ║
║  Gate 63A is preflight only. Do not run §4–§8 without a new  ║
║  operator message naming project, LOGIN role, and scope.     ║
╚══════════════════════════════════════════════════════════════╝
```

| Field | Value |
| --- | --- |
| Status | **PROCEDURE ONLY — NOT EXECUTED** |
| Project | `wmirifmgaftassgrfbyl` only |
| Prerequisite Alembic | `20261108_0005` |
| Proposed LOGIN | `cryptonova_api_login` |
| Companions | `PHASE_4D_GATE_63A_RUNTIME_CUTOVER_PREFLIGHT.md`, `PHASE_4D_GATE_63B_SECURITY_REMEDIATION_REPORT.md`, `PHASE_4D_GATE_63B_AUTH_SCHEMA_GRANT_PROPOSAL.md` |
| Local prep (63B) | Fail-closed `DATABASE_RUNTIME_URL` selection implemented (flag OFF); auth USAGE grant still remote-pending |

---

## 1. Purpose

Cut FastAPI off the BYPASSRLS `postgres` connection and onto a dedicated least-privilege LOGIN that inherits `cryptonova_api_runtime`, with JWT-verified transaction-local `auth.uid()` binding.

**Out of scope for Gate 63:** cloud writes, sync, historical import, exchange orders, Gate C2, deployment.

---

## 2. Preconditions checklist

- [ ] Gate 63B local remediation complete (fail-closed engine + local RLS/pool PASS)
- [ ] Auth schema USAGE grant authorized **and verified** (`has_schema_privilege(...)=true`) — grantor must be `supabase_admin` / dashboard path (`postgres` lacks GRANT OPTION)
- [ ] Operator approval names project `wmirifmgaftassgrfbyl` and LOGIN role
- [ ] Remote Alembic still `20261108_0005`
- [ ] `cryptonova_api_runtime` / `cryptonova_migrator` attributes unchanged
- [ ] Cloud write / sync / import / order flags OFF
- [ ] `RUNTIME_DB_IDENTITY_ENABLED` remains false until §6
- [ ] Session pooler URL (port **5432**), not transaction pooler (**6543**)
- [ ] `DATABASE_RUNTIME_URL` set offline; Alembic stays on legacy/admin URL (`sqlalchemy_url_legacy`)
- [ ] Rollback approval criteria agreed (privileged restore = security regression)

---

## 3. Safety envelope

| Control | Required |
| --- | --- |
| Target | `wmirifmgaftassgrfbyl` / `ap-southeast-2` only |
| Secrets | Offline password generation; never commit; never log URL passwords |
| App gates | Writes/sync/orders stay OFF |
| Pooler | Session mode for `SET LOCAL` GUC |
| Fail-closed | No silent fallback to `postgres` if runtime URL fails |

---

## 4. Proposed remote DDL (NON-EXECUTED)

### 4.1 Remediate auth schema USAGE (required before LOGIN cutover)

```sql
-- NON-EXECUTED — REQUIRES SEPARATE AUTHORIZATION
-- Must be run by a principal that can GRANT on schema auth (e.g. supabase_admin
-- via approved Supabase SQL path). postgres alone lacks GRANT OPTION on auth.
GRANT USAGE ON SCHEMA auth TO cryptonova_api_runtime;
-- Verify: has_schema_privilege('cryptonova_api_runtime','auth','USAGE') = true
```

### 4.2 Create dedicated LOGIN

```sql
-- NON-EXECUTED — REQUIRES SEPARATE AUTHORIZATION
-- Password generated offline; never paste into git/chat logs.
CREATE ROLE cryptonova_api_login
  LOGIN PASSWORD '<offline-secret>'
  NOSUPERUSER NOCREATEDB NOCREATEROLE NOBYPASSRLS
  INHERIT
  IN ROLE cryptonova_api_runtime;

-- Optional: ensure no unexpected memberships
-- (inspect pg_auth_members; do not add service_role / supabase_admin)
```

### 4.3 Do **not** in Gate 63

- DROP / ALTER `postgres`
- REASSIGN OWNED
- FORCE RLS (separate approval)
- GRANT DELETE to runtime
- Expand scheduler INSERT/UPDATE (Gate D)
- Create migrator LOGIN unless separately approved for Alembic-only use

---

## 5. Credential storage (NON-EXECUTED)

1. Generate strong password offline (password manager / `openssl rand -base64 32`).
2. Store as server-side secret: `DATABASE_RUNTIME_URL` (session pooler, `sslmode=require`, user `cryptonova_api_login`).
3. Keep privileged URL only for Alembic/break-glass as `DATABASE_URL` **or** rename to `DATABASE_ADMIN_URL` after app wiring supports it — **do not** leave FastAPI reading privileged URL when runtime mode is on.
4. Redact in logs (`redacted_database_url()`).
5. Rotate: ALTER ROLE password → update secret store → recycle API processes.

---

## 6. Application cutover sequence (NON-EXECUTED)

1. Explicit operator authorization recorded.
2. RO preflight inventory (roles, ACL USAGE auth, Alembic, flags).
3. Apply §4.1 then §4.2; re-verify ACL + membership inherit.
4. Controlled connectivity check as login (`SELECT 1`; `SELECT auth.uid()` with SET LOCAL) — **not** production traffic.
5. Config (authorized restart only): set `DATABASE_RUNTIME_URL` to session-pooler LOGIN URL (`sslmode=require`). Keep Alembic on privileged/admin URL via `sqlalchemy_url_legacy()` / `DATABASE_URL`.
6. Set `RUNTIME_DB_IDENTITY_ENABLED=true`. Engine path (`apps/api/app/runtime_db.py`) **requires** runtime URL, rejects privileged usernames, and **does not** fall back to `DATABASE_URL`. `configure_engine` probes live `session_user` / `rolbypassrls` and refuses BYPASSRLS sessions.
7. Health checks + owner isolation tests (§7).
8. Post-cutover RO verify: `session_user` is LOGIN; `rolbypassrls=false`; flags still OFF; cloud/trading gates unchanged.

---

## 7. Live Auth / RLS verification plan (future Gate 63 window)

| # | Test | Write? |
| --- | --- | --- |
| 1 | Two real Supabase Auth users A/B | No user creation in 63A |
| 2 | Valid JWT A → GUC → SELECT own only | Read / optional synthetic insert under separate write approval |
| 3 | Valid JWT B cannot see A | Read |
| 4 | Missing / invalid / expired JWT → 401 | No |
| 5 | Concurrent A/B requests; pool reuse | No |
| 6 | Role attrs still NOBYPASSRLS | RO catalog |
| 7 | API health | No |

Any remote INSERT for isolation proof requires **separate** write authorization and cleanup rules — Gate 63 cutover approval ≠ Gate C2.

---

## 8. Rollback

| Scenario | Action | Security note |
| --- | --- | --- |
| Login connect fails before traffic | Keep / restore privileged URL; leave `RUNTIME_DB_IDENTITY_ENABLED=false` | No regression if never cut over |
| Cutover live but RLS/auth broken | Explicit operator approval to temporarily restore privileged `DATABASE_URL` | **Security regression** — document window; re-disable identity flag |
| Bad LOGIN role | REVOKE / DROP LOGIN after app rolled back; keep base runtime role | Do not DROP `cryptonova_api_runtime` casually |
| Auth USAGE grant unwanted | REVOKE USAGE ON SCHEMA auth FROM runtime (authorized) | |

Rollback must **not** silently re-enable privileged production access without an explicit operator decision.

---

## 9. Abort conditions

Stop if: wrong project; Alembic ≠ `20261108_0005`; auth USAGE still false; LOGIN created with BYPASSRLS/SUPERUSER/NOINHERIT; membership missing; transaction pooler URL; write/sync/order flags ON; checksum/policy drift; engine falls back to postgres while identity enabled.

---

## 10. Non-execution attestation (Gate 63A)

This runbook was prepared without creating remote LOGIN roles, rotating credentials, changing FastAPI `DATABASE_URL`, enabling `RUNTIME_DB_IDENTITY_ENABLED`, cloud writes, sync, imports, exchange orders, deployment, or git push.
