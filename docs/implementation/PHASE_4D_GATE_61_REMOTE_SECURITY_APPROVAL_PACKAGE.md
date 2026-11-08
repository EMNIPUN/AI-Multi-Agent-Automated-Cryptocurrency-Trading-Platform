# Phase 4D Gate 61 — Remote Security Migration Approval Package

| Field | Value |
| --- | --- |
| Gate | **61 — approval package only** |
| Date | 2026-11-08 |
| Target project | `wmirifmgaftassgrfbyl` |
| Current Alembic | `20261107_0004` |
| Proposed Alembic | `20261108_0005` |
| Decision | **GO — READY FOR SEPARATE GATE 62 AUTHORIZATION** |
| Remote mutations this gate | **None** |

**This document does not authorize Gate 62 execution, Gate 63 credential cutover, or Gate C2 cloud writes.**

---

## 1. Executive summary

Read-only revalidation confirms the development Supabase project, revision, empty Phase 4D tables, and privileged `postgres` BYPASSRLS baseline are unchanged. Proposed Option A migration `20261108_0005` remains in `versions_proposed/` (not active). Local PostgreSQL RLS validation (Prompt 60) and Gate 61 security regression tests support requesting a **separate** Gate 62 apply.

Signal row delta expected on apply: **0**. Alembic metadata will change to `20261108_0005`.

---

## 2. Project verification

| Check | Result | Class |
| --- | --- | --- |
| Project ref | `wmirifmgaftassgrfbyl` | VERIFIED REMOTELY READ-ONLY |
| Host / region | `aws-0-ap-southeast-2.pooler.supabase.com` | VERIFIED REMOTELY READ-ONLY |
| Alembic | `20261107_0004` | VERIFIED REMOTELY READ-ONLY |
| Session user | `postgres` | VERIFIED REMOTELY READ-ONLY |
| `rolbypassrls` | `true` | VERIFIED REMOTELY READ-ONLY |
| `rolsuper` | `false` | VERIFIED REMOTELY READ-ONLY |
| Phase 4D row counts | all **0** | VERIFIED REMOTELY READ-ONLY |
| Cloud write/sync/order flags | OFF / unset | VERIFIED LOCALLY |
| `CRYPTONOVA_ALLOW_DEV_MIGRATIONS` | `false` | VERIFIED LOCALLY |
| Proposed file in active `versions/` | **No** | VERIFIED LOCALLY |

Tools: `scripts/_gate_c1_readonly_catalog.py`, `scripts/_option_a_readonly_rls_inventory.py`, `scripts/_gate_61_readonly_role_probe.py`.

---

## 3. Current role and RLS inventory

### Roles of interest (remote)

| Role | super | bypassrls | login | inherit | Notes |
| --- | --- | --- | --- | --- | --- |
| `postgres` | false | **true** | true | true | Current FastAPI / Alembic credential |
| `authenticated` | false | false | false | true | Existing SELECT policies |
| `anon` | false | false | false | true | Present |
| `authenticator` | false | false | true | false | Supabase-managed |
| `cryptonova_*` | — | — | — | — | **Count = 0** (not created) |

### Table ownership

All `app` application tables owned by **`postgres`**. RLS enabled (not FORCE) except `app.alembic_version` (no RLS).

### Existing policies

SELECT-own → role **`authenticated`** via `auth.uid()` on catalog, bindings, and Phase 4D tables. **No** INSERT/UPDATE policies today. **No** policies for `cryptonova_api_runtime`.

### Functions

`auth.uid()` exists; `postgres` can EXECUTE.

---

## 4. Approved-for-review migration content and checksum

| Item | Value |
| --- | --- |
| Path | `apps/api/alembic/versions_proposed/20261108_0005_option_a_least_privilege.py` |
| Revision | `20261108_0005` |
| Revises | `20261107_0004` |
| Active path | **Not promoted** |
| SHA-256 | `9e0efdd317926a7ce5959f87e77c60c122e87ec62c49345597840cc6307f318a` |
| Size | 6804 bytes |

Gate 62 must re-hash this file immediately before apply and abort on mismatch.

---

## 5. Exact proposed DDL scope (Gate 62 — not executed)

1. **CREATE ROLE** (idempotent IF NOT EXISTS):
   - `cryptonova_api_runtime` — NOLOGIN, NOSUPERUSER, NOCREATEDB, NOCREATEROLE, NOBYPASSRLS, **INHERIT**
   - `cryptonova_migrator` — same flags
2. **Schema grants:** `USAGE` on `app` → runtime + migrator; `USAGE` on `auth` → runtime
3. **Function grant:** `EXECUTE ON FUNCTION auth.uid()` → runtime
4. **Table grants (runtime):**
   - Signal write tables: `SELECT, INSERT, UPDATE` (no DELETE) on `signal_history`, `signal_agent_contributions`, `signal_risk_events`
   - Scheduler: `SELECT` only on `scheduler_evaluation_history`, `scheduler_audit`
   - Catalog: `SELECT` on `agent_decisions`, `system_events`, `strategy_configs`, `exchange_account_bindings`
5. **Table grants (migrator):** `SELECT, INSERT, UPDATE, DELETE` on listed app tables; `CREATE ON SCHEMA app`
6. **Policies (runtime):** SELECT/INSERT/UPDATE own on signal write tables; SELECT own on scheduler + catalog (bindings: active + own)
7. **Alembic:** version row → `20261108_0005`
8. **Out of Gate 62 scope:** LOGIN password roles, FastAPI URL cutover, FORCE RLS, ownership REASSIGN, cloud writes

**Application signal data changes: none expected.**

---

## 6. Role / grant / policy impact matrix

| Object | Before | After Gate 62 |
| --- | --- | --- |
| Signal rows | 0 | 0 |
| `postgres` privileges | Unchanged (still privileged) | Unchanged |
| FastAPI effective role | Still `postgres` until Gate 63 | Still `postgres` |
| New runtime policies | Absent | Present for `cryptonova_api_runtime` |
| Existing `authenticated` policies | Unchanged | Unchanged |
| RLS enforcement for API | Still bypassed (BYPASSRLS) | Still bypassed until Gate 63 |

---

## 7. Security risks

| Risk | Severity | Mitigation |
| --- | --- | --- |
| Apply on wrong project | Critical | Ref check + halt |
| Free-plan cannot CREATE ROLE | High | Abort; document Supabase limit |
| `GRANT EXECUTE ON auth.uid()` denied | Medium | Abort; use SQL editor with elevated rights |
| Partial apply (roles without policies) | High | Abort + manual revoke/drop policy restore |
| Believing Gate 62 removes BYPASSRLS for FastAPI | High | Requires Gate 63 cutover |
| Migrator cannot ALTER postgres-owned tables later | Medium | Documented residual — future DDL may still need privileged connection |
| Alembic downgrade incomplete for roles | Medium | No DROP ROLE in downgrade; manual cleanup |
| Supabase Free backup/PITR absent | Medium | Accepted residual for personal-dev (Gate B) |

### Migrator vs postgres-owned tables

Gate 62 DDL runs as the **current privileged migration connection** (`postgres`), which can CREATE POLICY/GRANT on owned tables. The new `cryptonova_migrator` role receiving DML + `CREATE ON SCHEMA` is **not** equivalent to ownership: future `ALTER TABLE` on existing `postgres`-owned objects may still require the privileged path unless a later approved ownership strategy lands. This is an accepted residual, not a Gate 62 apply blocker.

### Supabase CREATE ROLE permission

Not verified by executing CREATE (forbidden). Assumed feasible under project owner SQL / Alembic as `postgres`. Treat failure at Gate 62 as abort.

---

## 8. Recovery and rollback plan

### Pre-change

1. RO catalog + role probe + RLS inventory (save outputs).
2. Confirm SHA-256 of proposed file.
3. Confirm flags OFF.
4. Confirm Free-plan residual accepted.

### On failure mid-apply

1. Stop; do not cut over credentials.
2. Record Alembic version (`SELECT * FROM app.alembic_version`).
3. If roles/policies partially exist: REVOKE/DROP POLICY for runtime/migrator as needed; do not DROP ROLE until membership audit.
4. Prefer restoring to known `20261107_0004` metadata only if safe; do not invent data restores.

### Downgrade limitations

- `downgrade()` drops runtime/migrator policies and revokes grants.
- Does **not** DROP ROLE.
- Does **not** restore secrets/LOGIN wrappers.
- Does **not** provide PITR.

### Halt conditions

Wrong project/region; checksum mismatch; CREATE ROLE failure; unexpected signal row growth; any exchange/cloud-write flag ON; Auth schema unexpected mutation beyond intended GRANT EXECUTE.

---

## 9. Read-only post-migration checks (Gate 62 after-apply)

```text
# illustrative — run only after Gate 62 authorization
uv run python scripts/_gate_c1_readonly_catalog.py
uv run python scripts/_option_a_readonly_rls_inventory.py
uv run python scripts/_gate_61_readonly_role_probe.py
```

Expect:

- Alembic `20261108_0005`
- `cryptonova_role_count` ≥ 2
- Phase 4D counts still 0
- New `*_runtime_*` policies present
- FastAPI still on `postgres` until Gate 63
- All trading/cloud flags OFF

---

## 10. Outstanding blockers

| Item | Blocks Gate 61 GO? | Blocks Gate 62? | Blocks Gate 63 / C2? |
| --- | --- | --- | --- |
| Explicit Gate 62 operator text | No (this package) | **Yes** | — |
| CREATE ROLE feasibility live | No (documented residual) | Yes if fails at apply | — |
| Runtime LOGIN + URL cutover | No | No (out of scope) | **Yes for RLS enforcement** |
| Live Auth GUC E2E | No | No | Recommended before multi-user |

No unexpected project/schema mismatch found.

---

## 11. Required operator approval wording (Gate 62)

> I authorize **Gate 62** remote security migration for CryptoNova development project **`wmirifmgaftassgrfbyl`** only.  
> Scope: promote and apply Alembic revision **`20261108_0005`** (SHA-256 `9e0efdd317926a7ce5959f87e77c60c122e87ec62c49345597840cc6307f318a`) creating least-privilege roles/grants/policies per Option A.  
> Expected signal row changes: **zero**. Alembic metadata may update.  
> I accept Free-plan backup residual and incomplete Alembic role rollback.  
> **Not authorized:** Gate 63 credential cutover, Gate C2 cloud writes, cloud sync, historical import, exchange orders, deployment, git push.  
> Halt on wrong project, checksum mismatch, or unexpected data changes.

---

## 12. Final decision

### **GO — READY FOR SEPARATE GATE 62 AUTHORIZATION**

Gate 61 approval package is complete. Do **not** execute migration until the Gate 62 wording above (or equivalent) is provided.

---

## Local validation (Gate 61)

| Suite | Result |
| --- | --- |
| Option A + C1 + auth pytest | **37 passed**, **1 skipped** (disposable PG port down) |
| Cloud/trading flags | OFF |

---

## Gate separation reminder

| Gate | Purpose | Status |
| --- | --- | --- |
| 61 | Approval package | **This document** |
| 62 | Apply `20261108_0005` remotely | Awaiting approval |
| 63 | FastAPI runtime credential cutover | Not started |
| C2 | Synthetic cloud write | Not started |
