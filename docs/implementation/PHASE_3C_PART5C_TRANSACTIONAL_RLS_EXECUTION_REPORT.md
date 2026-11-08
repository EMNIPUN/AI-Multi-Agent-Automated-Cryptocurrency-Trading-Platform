# Phase 3C Part 5C — Transactional RLS Execution Report

| Field | Value |
|-------|-------|
| Date | 2026-11-06 |
| Approval | `DATA_API_VERIFIED: app not exposed` + `APPROVE_TRANSACTIONAL_RLS_PART5B` |
| Target | Development `wmirifmgaftassgrfbyl` |
| Runner | `scripts/run_transactional_rls_isolation.py --execute` |
| Result | **PASS** (`EXIT=0`) |

---

## Pre-execution gates

| Check | Result |
|-------|--------|
| `CRYPTONOVA_DB_TARGET` | development |
| Project ref | `wmirifmgaftassgrfbyl` |
| Host / pooler | `aws-0-ap-southeast-2.pooler.supabase.com` / session |
| Alembic | `20261105_0003` |
| Data API gate env | `CRYPTONOVA_DATA_API_APP_NOT_EXPOSED=yes` |
| Approval env | `CRYPTONOVA_APPROVE_TRANSACTIONAL_RLS=yes` |
| Migrations flag | false (not used) |

Runner log:

```
RLS_PROBE_IDENTITY_OK
project_ref=wmirifmgaftassgrfbyl host=aws-0-ap-southeast-2.pooler.supabase.com pooler=session_pooler
RLS_PROBE_DRY_RUN_OK
alembic=20261105_0003 set_role=True bypassrls=True fix=agent_decisions.strategy_id_required
```

---

## In-transaction assertions (role `authenticated`)

Executed on **one** connection; inserts + named-table GRANTs + `SET LOCAL ROLE authenticated` + JWT claim GUCs; hard `_assert_eq` failures.

| Assertion | Expected | Result |
|-----------|----------|--------|
| `auth.uid()` = User A | match | PASS |
| User A agent/events/strategies | 1 / 1 / 1 | PASS |
| User A bindings visible | 1 (`active` only) | PASS |
| User A pending/revoked hidden | yes | PASS |
| `auth.uid()` = User B | match | PASS |
| User B agent / bindings | 1 / 1 (own only) | PASS |
| Missing `sub` | 0 agents | PASS |
| Invalid `sub` | 0 agents / 0 bindings | PASS |
| Transaction end | **ROLLBACK** (never COMMIT) | PASS |

Runner log:

```
RLS_PROBE_EXECUTE_ASSERTIONS_OK
tx=rolled_back
```

---

## Independent post-rollback verification

New connection, `SET TRANSACTION READ ONLY`:

| Check | Expected | Result |
|-------|----------|--------|
| Synth rows (all 4 tables) | 0 | PASS |
| `authenticated` schema USAGE | false | PASS |
| `authenticated` SELECT on app tables | false | PASS |

Runner log:

```
RLS_PROBE_POST_ROLLBACK_OK
grants_cleared=True
RLS_PROBE_EXECUTE_PASS
EXIT=0
```

---

## Explicit non-actions

| Item | Status |
|------|--------|
| Migrations | None |
| Auth users created | None |
| Private wallet reads | Still disabled |
| Bybit orders | None |
| Git commit/push | None |
| Persistent GRANTs | None remaining |

---

## Interpretation

Class C PostgreSQL RLS isolation under role `authenticated` with synthetic `auth.uid()` claims is **PASS** on the approved development database.

This does **not** by itself prove:

- Browser / JWKS Auth E2E (Class D)
- FastAPI path isolation under `postgres` BYPASSRLS (Class B remains application-layer)
- Production readiness

`PRIVATE_DATA_READS_ENABLED` remains false.
