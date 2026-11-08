# Phase 4D Gate 63B — Auth Schema USAGE Grant Proposal

```
╔══════════════════════════════════════════════════════════════╗
║  NON-EXECUTED — SEPARATE OPERATOR APPROVAL REQUIRED          ║
║  Do not run against Supabase until explicitly authorized.    ║
╚══════════════════════════════════════════════════════════════╝
```

| Field | Value |
| --- | --- |
| Project | `wmirifmgaftassgrfbyl` only |
| Target role | `cryptonova_api_runtime` |
| Schema | `auth` |
| Proposed privilege | `USAGE` |
| Status | **PROPOSAL ONLY** |

---

## 1. Problem statement

Gate 62 attempted:

```sql
GRANT USAGE ON SCHEMA auth TO cryptonova_api_runtime;
```

Post-apply RO inventory shows:

| Probe | Result |
| --- | --- |
| `auth` owner | `supabase_admin` |
| `has_schema_privilege(runtime,'auth','USAGE')` | **false** |
| `has_function_privilege(runtime,'auth.uid()','EXECUTE')` | **true** |
| `auth.uid()` EXECUTE via PUBLIC | present |
| `postgres` ACL on `auth` | USAGE, **`is_grantable=false`** |
| `postgres.rolsuper` | false |

Root cause: `postgres` is not the schema owner and lacks GRANT OPTION on `auth`. The Gate 62 statement did not produce an effective ACL entry for `cryptonova_api_runtime`. Future grants must use a principal that can grant on `auth` (typically `supabase_admin` / Supabase SQL editor privileged path).

---

## 2. Local proof (disposable PG 18.6 on 127.0.0.1:55432)

Harness: `scripts/_gate_63b_local_auth_usage_harness.py`

| Case | Result |
| --- | --- |
| Without schema USAGE, `SELECT auth.uid()` as LOGIN | **DENIED** |
| Without schema USAGE, RLS policy using `auth.uid()` | Observed **succeed** on PG 18.6 (SQL function evaluation residual) |
| With `GRANT USAGE ON SCHEMA auth` | Direct + policy paths work; owner isolation PASS |
| LOGIN inherits runtime grants | PASS (INHERIT membership) |

Conclusion: **minimum explicit remediation remains `USAGE ON SCHEMA auth`** so:

1. Direct/diagnostic `auth.uid()` calls work.
2. Behavior is portable across PostgreSQL / Supabase policy evaluation edges.
3. Effective privilege inventory matches operator intent.

SECURITY DEFINER wrappers around `auth.uid()` were **not** adopted (threat-model cost; not required if USAGE is granted).

---

## 3. Exact proposed SQL

```sql
-- NON-EXECUTED — SEPARATE OPERATOR APPROVAL REQUIRED
-- Project: wmirifmgaftassgrfbyl only
-- Grantor: must hold GRANT OPTION on schema auth (supabase_admin / approved dashboard SQL).
-- Do NOT rely on session role postgres for this grant (USAGE without GRANT OPTION).

GRANT USAGE ON SCHEMA auth TO cryptonova_api_runtime;
```

No other schemas. No GRANT on `auth` tables. No CREATE on `auth`. No LOGIN creation in this proposal.

---

## 4. Preflight queries (read-only)

```sql
-- NON-EXECUTED operator checklist (RO)
SELECT current_database(), session_user, current_user;
SELECT version_num FROM app.alembic_version;  -- expect 20261108_0005
SELECT pg_get_userbyid(n.nspowner) AS auth_owner
FROM pg_namespace n WHERE nspname = 'auth';
SELECT has_schema_privilege('cryptonova_api_runtime','auth','USAGE');  -- expect false before
SELECT has_function_privilege('cryptonova_api_runtime','auth.uid()','EXECUTE');
SELECT nspacl::text FROM pg_namespace WHERE nspname = 'auth';
```

---

## 5. Post-change verification

```sql
-- NON-EXECUTED verification after authorized grant
SELECT has_schema_privilege('cryptonova_api_runtime','auth','USAGE');  -- expect true
SELECT nspacl::text FROM pg_namespace WHERE nspname = 'auth';
-- Confirm no unexpected CREATE/WRITE on auth:
SELECT has_schema_privilege('cryptonova_api_runtime','auth','CREATE');  -- expect false
```

Future LOGIN `cryptonova_api_login IN ROLE cryptonova_api_runtime` (INHERIT) inherits USAGE without extra grants.

---

## 6. Rollback SQL

```sql
-- NON-EXECUTED — SEPARATE OPERATOR APPROVAL REQUIRED
REVOKE USAGE ON SCHEMA auth FROM cryptonova_api_runtime;
```

Safe if no production traffic depends on runtime LOGIN yet (Gate 63 not executed).

---

## 7. Security impact

| Aspect | Assessment |
| --- | --- |
| Objects exposed | Schema lookup for `auth.*` callables only; not table DML on Auth users |
| Escalation | Does not grant BYPASSRLS, SUPERUSER, or auth table privileges |
| Inheritance | LOGIN members inherit USAGE |
| Necessity | Required for explicit `auth.uid()` resolution under least-privilege LOGIN |
| Alternative | SECURITY DEFINER helper — rejected without separate threat model |

---

## 8. Required operator authorization

A new message must name:

1. Project `wmirifmgaftassgrfbyl`
2. Exact statement `GRANT USAGE ON SCHEMA auth TO cryptonova_api_runtime`
3. Acknowledgement that grantor is **not** ordinary `postgres` ACL (dashboard / supabase_admin path)
4. Explicit exclusion of LOGIN creation / credential cutover unless separately listed

Until then: **DO NOT EXECUTE**.
