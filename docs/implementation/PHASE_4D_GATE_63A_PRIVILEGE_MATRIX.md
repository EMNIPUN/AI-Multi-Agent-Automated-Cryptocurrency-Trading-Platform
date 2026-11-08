# Phase 4D Gate 63A — Effective Privilege Matrix

| Field | Value |
| --- | --- |
| Project | `wmirifmgaftassgrfbyl` |
| Alembic | `20261108_0005` |
| Date | 2026-11-08 |
| Mode | Read-only remote catalog + design analysis |
| LOGIN role | **Proposed only** — `cryptonova_api_login` **NOT CREATED** |

Legend: **Y** = yes / granted · **N** = no · **P** = proposed (not remote) · **—** = n/a

---

## 1. Role attributes (observed / proposed)

| Attribute | `postgres` (current FastAPI) | `cryptonova_api_runtime` | `cryptonova_migrator` | `cryptonova_api_login` (proposed) |
| --- | --- | --- | --- | --- |
| LOGIN | Y | N | N | **P Y** |
| SUPERUSER | N | N | N | **P N** |
| BYPASSRLS | **Y** | **N** | **N** | **P N** |
| CREATEDB | Y | N | N | **P N** |
| CREATEROLE | Y | N | N | **P N** |
| INHERIT (role attr) | Y | Y | Y | **P Y** |
| Member of runtime | — | — | N | **P Y** (`IN ROLE cryptonova_api_runtime`, inheriting membership) |
| Table owner | Y (all `app.*`) | N | N | **P N** |

Membership note (PostgreSQL 17/18): privileges granted to `cryptonova_api_runtime` are available to an inheriting LOGIN member **without** `SET ROLE` when the LOGIN role uses default **INHERIT** and membership is not `SET`/`INHERIT false`. A **NOINHERIT** LOGIN does **not** receive grants (validated previously on disposable PG18 harness).

---

## 2. Connection / schema / function

| Privilege | `postgres` | runtime | migrator | login (proposed) |
| --- | --- | --- | --- | --- |
| CONNECT to DB | Y | via LOGIN member | via future migrator LOGIN | **P Y** |
| USAGE `app` | Y | **Y** | **Y** | **P via inherit** |
| CREATE ON `app` | Y | **N** | **Y** | **P N** |
| USAGE `auth` | **Y** | **N (gap)** | N | **P needs fix** |
| EXECUTE `auth.uid()` | Y | **Y** (also PUBLIC EXECUTE) | — | **P Y** |
| RLS bypass | **Y** | N | N | **P N** |
| SET ROLE to privileged | elevated | N | N | **P N** |

**Gap:** Remote ACL on schema `auth` lists USAGE for `anon` / `authenticated` / `service_role` / `postgres` / admins — **not** `cryptonova_api_runtime`. `has_schema_privilege(runtime, auth, USAGE) = false`. Gate 62 `GRANT USAGE ON SCHEMA auth` did not produce an effective ACL entry (likely grantor lacked GRANT OPTION; `auth` owned by `supabase_admin`). Gate 63 must remediate with an authorized grant path before cutover.

---

## 3. Table DML (effective for runtime; login inherits)

| Table | SELECT | INSERT | UPDATE | DELETE | Notes |
| --- | --- | --- | --- | --- | --- |
| `signal_history` | Y | Y | Y | **N** | RLS own-row policies |
| `signal_agent_contributions` | Y | Y | Y | **N** | |
| `signal_risk_events` | Y | Y | Y | **N** | |
| `scheduler_evaluation_history` | Y | N | N | **N** | SELECT-only until Gate D |
| `scheduler_audit` | Y | N | N | **N** | SELECT-only |
| `agent_decisions` | Y | N | N | **N** | catalog |
| `system_events` | Y | N | N | **N** | |
| `strategy_configs` | Y | N | N | **N** | |
| `exchange_account_bindings` | Y | N | N | **N** | active-status RLS |
| `alembic_version` | via postgres | — | — | — | no runtime grant |

Migrator: SELECT/INSERT/UPDATE/DELETE on listed app tables + CREATE ON SCHEMA `app`. Still insufficient alone to ALTER postgres-owned tables without ownership transfer.

`postgres` connection: full table privileges + **BYPASSRLS** → application owner filters remain mandatory until cutover.

---

## 4. Application path privilege needs

| Path | Required DB privs | Today | After Gate 63 (intended) |
| --- | --- | --- | --- |
| Cloud history GET | SELECT + RLS + `auth.uid` | app filter; BYPASSRLS | login + GUC + RLS |
| Cloud writes (future C2) | INSERT/UPDATE + RLS | gated OFF | same; gates still required |
| Scheduler sync (future D) | INSERT/UPDATE on scheduler | gated OFF; runtime SELECT only | needs separate grant expansion |
| Catalog reads | SELECT + RLS | `PRIVATE_DATA_READS` OFF | login inherit SELECT |
| Health `SELECT 1` | CONNECT | postgres | login CONNECT |
| Alembic migrations | DDL/DML elevated | postgres URL | keep separate migrator/admin URL |

Sequences / identity: UUID PKs generated in app — no sequence USAGE required for Phase 4D tables observed.

INSERT … RETURNING: covered by INSERT + SELECT under RLS.

Foreign keys: INSERT into contributions/risk requires parent visibility under RLS — same owner scope.

---

## 5. Unnecessary privileges (must remain absent on login/runtime)

- DELETE on signal/scheduler/catalog (runtime)
- CREATE/ALTER/DROP on schema or tables (runtime/login)
- BYPASSRLS / SUPERUSER / CREATEROLE
- Membership in `supabase_admin`, `service_role`, `authenticator`
- Table ownership
- Direct grants beyond those on `cryptonova_api_runtime` (prefer inherit-only LOGIN)

---

## 6. Acceptance for Gate 63 design

| Item | Status |
| --- | --- |
| Runtime NOBYPASSRLS + grants match Gate 62 | **PASS** |
| No runtime DELETE | **PASS** |
| Login inherit-without-SET-ROLE design | **PASS** (local prior evidence; remote login absent) |
| `auth` schema USAGE for runtime | **CONDITIONAL / remediation required** |
| `DATABASE_RUNTIME_URL` fail-closed wiring | **CONDITIONAL** (config field exists; engine still uses privileged `DATABASE_URL`) |
