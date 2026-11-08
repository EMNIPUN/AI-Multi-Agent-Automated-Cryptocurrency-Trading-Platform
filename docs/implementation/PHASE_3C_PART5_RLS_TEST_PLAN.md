# Phase 3C Part 5 — Real RLS Isolation Test Plan

| Field | Value |
|-------|--------|
| Status | **UPDATED Part 5B — AWAITING OPERATOR APPROVAL** |
| Preferred method | **Single-transaction inserts + narrow GRANTs + SET ROLE + ROLLBACK** |
| Executable detail | `PHASE_3C_PART5B_TRANSACTIONAL_RLS_EXECUTION_PLAN.md` |
| Target project | `wmirifmgaftassgrfbyl` (development only) |
| Alembic revision required | `20261105_0003` |
| Writes executed | **None** |

---

## Why approval is required

Catalog inspection proves policies **exist**, but does **not** prove they **enforce** isolation:

1. FastAPI connects as `postgres` with **`rolbypassrls=true`** — RLS is skipped on the application path.
2. Role `authenticated` currently has **no** persistent `USAGE` / `SELECT` on schema `app`.
3. Application tables are **empty** — cross-user denial needs synthetic rows.
4. JWT claim GUCs are test inputs — not cryptographically verified Auth sessions.

---

## Separation of test classes

| Class | What it proves | Current status |
|-------|----------------|----------------|
| A. Catalog / policy structure | RLS on; policy text; roles | **Done** |
| B. FastAPI ownership | JWT + WHERE + bindings | **Done offline** |
| C. PostgreSQL RLS as `authenticated` | Policy enforcement with `auth.uid()` | **Blocked on approval** (transactional plan ready) |
| D. Live Auth E2E | Browser → Next → FastAPI JWT | Pending anon key + Auth users (separate) |

Do not conflate B with C.

---

## Preferred execution (Part 5B)

**Do not use persistent GRANT/REVOKE or marker DELETE as the primary path.**

Use one connection:

1. Verify development identity + revision.
2. `BEGIN`
3. Insert marked synthetic rows.
4. `GRANT USAGE` + **named-table** `SELECT` to `authenticated` only.
5. `SET LOCAL ROLE authenticated` + `set_config` for JWT claims.
6. Assert User A / User B / missing / invalid / pending+revoked visibility.
7. `RESET ROLE`
8. `ROLLBACK`
9. **New** read-only session: verify zero synthetic rows and no lingering grants.

Full SQL: `docs/implementation/PHASE_3C_PART5B_TRANSACTIONAL_RLS_EXECUTION_PLAN.md`.

### Deprecated for primary path

- Persistent `GRANT SELECT ON ALL TABLES IN SCHEMA app`
- Post-hoc `DELETE` cleanup as the success path (still available as emergency if ROLLBACK fails)

### Alternative (only if transactional path blocked)

Disposable probe role + matching policies (DDL) — requires **separate** approval; treat as migration-like.

Testing only as `postgres` remains **rejected** for Class C.

---

## Synthetic users

| Alias | UUID |
|-------|------|
| User A | `aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaa1` |
| User B | `bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbb2` |

Marker: `phase3c_part5b_rls_synth` (see Part 5B plan for exact column usage).

---

## Scenarios (Class C)

| # | Scenario | Expected |
|---|----------|----------|
| 1 | User A reads own rows | Visible |
| 2 | User A cannot read User B | Empty |
| 3 | User B cannot read User A | Empty |
| 4 | Missing JWT subject | Empty |
| 5 | Invalid JWT subject | Empty |
| 6 | Pending binding | Hidden by policy |
| 7 | Revoked binding | Hidden by policy |
| 8 | Active binding own only | Visible |
| 9 | Post-ROLLBACK persistence check | Zero rows; grants false |

Unauthenticated / `anon`, FastAPI service-role rejection, telemetry scope, and cross-env binding remain Class B / grant-matrix checks as documented in Part 5B.

---

## Auth users

Not required for Class C (GUC-based `auth.uid()`).  
Class D live E2E Auth users require **separate** approval.

---

## Operator approval

Approve via the Part 5B transactional plan stop condition:

`APPROVE_TRANSACTIONAL_RLS_PART5B`

Prerequisites: Data API confirms `app` not exposed; development identity unchanged.
