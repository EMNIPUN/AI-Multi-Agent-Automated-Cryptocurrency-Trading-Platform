# Phase 4D Option A — Security Migration Plan (NON-EXECUTED)

| Field | Value |
| --- | --- |
| Status | **PENDING APPROVAL — NOT EXECUTED** |
| Target project | `wmirifmgaftassgrfbyl` only |
| Depends on revision | `20261107_0004` |
| Proposed revision | `20261108_0005` |
| Draft location | `apps/api/alembic/versions_proposed/20261108_0005_option_a_least_privilege.py` |

**Do not move this file into `alembic/versions/` or run `alembic upgrade` without a separate Option A remote security-change approval.**

---

## 1. Preconditions

1. Project ref verified = `wmirifmgaftassgrfbyl`.
2. Alembic head = `20261107_0004`.
3. Cloud write/sync/import/order flags OFF.
4. `CRYPTONOVA_ALLOW_DEV_MIGRATIONS` only enabled for the approved migration window.
5. Operator has prepared strong passwords for LOGIN roles (never commit secrets).
6. SQLite SoT and app remain operational without Supabase writes.
7. Read-only pre-change inventory captured (`scripts/_option_a_readonly_rls_inventory.py`).

---

## 2. Proposed roles (conceptual SQL)

```sql
-- Base roles MUST use INHERIT so LOGIN members receive GRANTs (validated on PG 18).
CREATE ROLE cryptonova_api_runtime NOLOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE NOBYPASSRLS INHERIT;
CREATE ROLE cryptonova_migrator NOLOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE NOBYPASSRLS INHERIT;
-- LOGIN wrapper MUST also be INHERIT (default). NOINHERIT login will NOT see base grants
-- without SET ROLE (proven locally).
-- CREATE ROLE cryptonova_api_runtime_login LOGIN PASSWORD '…' INHERIT IN ROLE cryptonova_api_runtime;
```

Scheduler tables: **SELECT only** for runtime until Gate D. Signal tables: SELECT/INSERT/UPDATE, no DELETE.

Supabase may require SQL editor / dashboard steps; validate Free-plan role limits before apply.

---

## 3. Proposed grants

```sql
GRANT USAGE ON SCHEMA app TO cryptonova_api_runtime;
GRANT SELECT, INSERT, UPDATE ON
  app.signal_history,
  app.signal_agent_contributions,
  app.signal_risk_events,
  app.scheduler_evaluation_history,
  app.scheduler_audit
TO cryptonova_api_runtime;
-- No DELETE for runtime by default.

GRANT SELECT ON
  app.agent_decisions,
  app.system_events,
  app.strategy_configs,
  app.exchange_account_bindings
TO cryptonova_api_runtime;
```

Migrator: broader DML/DDL as required for Alembic only — never wired to FastAPI `DATABASE_URL`.

---

## 4. Proposed policies (runtime)

For each Phase 4D signal/scheduler table:

```sql
CREATE POLICY <table>_runtime_select_own ON app.<table>
  FOR SELECT TO cryptonova_api_runtime
  USING (owner_user_id = auth.uid());

CREATE POLICY <table>_runtime_insert_own ON app.<table>
  FOR INSERT TO cryptonova_api_runtime
  WITH CHECK (owner_user_id = auth.uid());

CREATE POLICY <table>_runtime_update_own ON app.<table>
  FOR UPDATE TO cryptonova_api_runtime
  USING (owner_user_id = auth.uid())
  WITH CHECK (owner_user_id = auth.uid());
```

Retain existing `TO authenticated` SELECT policies.

**Do not FORCE RLS** in the first remote change unless separately approved (impacts table-owner behavior).

---

## 5. Expected object changes

| Object | Change |
| --- | --- |
| Roles | + `cryptonova_api_runtime`, + `cryptonova_migrator` (+ optional LOGIN wrappers) |
| Grants | schema USAGE; table SELECT/INSERT/UPDATE as above |
| Policies | +3 per signal/scheduler table for runtime; +SELECT for catalog |
| Table ownership | **Unchanged** (remain non-runtime) |
| Data rows | **Unchanged** (no DML) |
| Alembic version | → `20261108_0005` after apply |

---

## 6. Runtime connection switch (after DDL)

1. Create LOGIN role + password in Supabase.
2. Set `DATABASE_RUNTIME_URL` (or replace `DATABASE_URL`) to runtime credentials — **separate approval**.
3. Set Alembic / ops to `DATABASE_MIGRATOR_URL`.
4. Enable `RUNTIME_DB_IDENTITY_ENABLED=true` only after runtime role verified.
5. Restart API process / clear SQLAlchemy pool.
6. Verify `current_user`, `rolbypassrls=false`, cannot SELECT foreign owner rows.

Prefer genuine runtime credentials over `SET LOCAL ROLE` from `postgres`.

---

## 7. Recovery / rollback limitations

| Action | Reversible? | Notes |
| --- | --- | --- |
| DROP POLICY | Yes | May briefly affect Data API if wrong policy dropped |
| REVOKE grants | Yes | Can break API until restored |
| DROP ROLE | Only if no dependencies | Must drop LOGIN members first |
| Alembic downgrade | Partial | Does **not** auto DROP ROLE in draft; operator cleans roles |
| Credential switch | Manual | Keep previous secret offline until verified |
| FORCE RLS (if ever applied) | Careful | Can lock out owners |

**Do not assume** Alembic downgrade fully restores prior privilege state.

Abort if: wrong project, unexpected grants on `auth`/`storage`, inability to create NOBYPASSRLS role, or app health fails after switch.

---

## 8. Required operator approvals (separate gates)

1. **Option A remote security-change approval** — apply pending revision / SQL package.
2. **Runtime credential cutover approval** — point FastAPI at runtime URL.
3. Gate C2 synthetic write remains a **separate** approval after (1)–(2) preferred.

---

## 9. Non-execution attestation

This plan and the draft under `versions_proposed/` were prepared without:

- CREATE/ALTER ROLE on Supabase
- GRANT/REVOKE on Supabase
- Policy DDL on Supabase
- Alembic upgrade
- Credential rotation in live `.env`
