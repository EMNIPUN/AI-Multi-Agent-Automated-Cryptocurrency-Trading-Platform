# Phase 3C Part 5D — Database Role Security Review

| Field | Value |
|-------|-------|
| Date | 2026-11-06 |
| Scope | Read-only architecture review |
| Role / grant changes | **None** |

---

## 1. Current risk: API connects as `postgres` (BYPASSRLS)

| Fact | Evidence |
|------|----------|
| Connection role | `postgres` (pooler `postgres.wmirifmgaftassgrfbyl`) |
| `rolbypassrls` | **true** |
| FORCE RLS | **false** |
| Per-request `SET ROLE` / JWT GUCs | **Not used** in FastAPI |

**Consequence:** PostgreSQL RLS policies do **not** constrain FastAPI SQL. Class C PASS proves policies for role `authenticated` only.

---

## 2. Private-data query audit (application filters)

### Catalog (`catalog_service.py`)

| Query | Owner filter |
|-------|----------------|
| `list_agent_decisions` | `AgentDecision.owner_user_id == owner` |
| `list_system_events` | `SystemEvent.owner_user_id == owner` (+ blocked event types) |
| `list_strategies` | `StrategyConfig.owner_user_id == owner` |

Gate: `require_private_catalog_access` → JWT + `PRIVATE_DATA_READS_ENABLED`.

**Unfiltered catalog list:** none found.

### Bindings (`binding_store.py` + `bindings.py`)

| Method | SQL owner filter | Caller protection |
|--------|------------------|-------------------|
| `list_for_owner` | Yes | Authz |
| `find_active` | Yes (+ status) | Authz |
| `get(id)` | **No** (PK only) | `require_active_binding_for_principal` compares `owner_user_id` |
| `find_by_telemetry_scope` | **No** (scope only) | `assert_telemetry_scope_access` after owner binding |
| `find_active_by_credential_ref` | No owner (cred uniqueness) | Enrollment path only |

### Wallet / telemetry routes

Owner-bound path always goes through `require_active_binding_for_principal` before credential resolution / ledger read.

Operator-local path: loopback diagnostic **without** JWT — separate from multi-user Auth; break-glass on Next is **off**.

### Residual risk

A future route that returns `store.get(id)` without the ownership assert would leak under BYPASSRLS. Mitigations: code review, tests, eventual non-bypass role.

---

## 3. Worker / internal access separation (design)

| Actor | Needs | Proposed role |
|-------|-------|---------------|
| Alembic / schema ops | DDL | Elevated `postgres` or migration role (operator-only) |
| FastAPI user reads | SELECT owned rows | `cryptonova_api_runtime` **no BYPASSRLS** |
| Worker telemetry writers | Append events / decisions for a known scope | `cryptonova_worker_runtime` with narrow INSERT + optional RLS using fixed GUC / service principal — **separate approval** |
| Browser / Data API | None on `app` | Keep `app` unexposed; no GRANTs to `anon` |

Workers must **not** share end-user JWT impersonation. Prefer explicit `owner_user_id` stamped at write time from verified binding enrollment, not from client input.

---

## 4. Least-privilege application role (proposal only — not applied)

Sketch (extends `apps/api/sql/runtime_role_recommendations.sql`):

```sql
-- NOT EXECUTED in Part 5D
CREATE ROLE cryptonova_api_runtime NOINHERIT LOGIN PASSWORD /* operator secret */;
GRANT USAGE ON SCHEMA app TO cryptonova_api_runtime;
GRANT SELECT ON
  app.agent_decisions,
  app.system_events,
  app.strategy_configs,
  app.exchange_account_bindings
TO cryptonova_api_runtime;

-- Policies currently TO authenticated; add matching policies OR
-- SET LOCAL ROLE + request.jwt.claim.sub per request (pool-safe design required).

CREATE POLICY agent_decisions_select_own_api
  ON app.agent_decisions FOR SELECT TO cryptonova_api_runtime
  USING (owner_user_id IS NOT NULL AND owner_user_id = auth.uid());
-- … mirror for other tables; bindings also require status = 'active'
```

### Adoption requirements (future approval)

1. Dual connection URLs: migrate vs runtime.
2. Per-request `set_config('request.jwt.claim.sub', principal.user_id, true)` **after** JWT verify, on a **non-pooled cross-request** session or with careful reset.
3. Policy set for `cryptonova_api_runtime` (Class C already validated pattern for `authenticated`).
4. Keep FORCE RLS off until runtime role is proven (FORCE would also bind table owner — high risk).
5. Integration tests: runtime role cannot read cross-tenant rows even if app filter regresses.

**Part 5D does not create this role.**

---

## 5. Verdict

| Item | Result |
|------|--------|
| BYPASSRLS risk documented | Yes |
| Private queries audited | Yes — filters present; PK/scope lookups caller-guarded |
| Least-privilege design | Prepared |
| Roles/grants changed | **None** |
