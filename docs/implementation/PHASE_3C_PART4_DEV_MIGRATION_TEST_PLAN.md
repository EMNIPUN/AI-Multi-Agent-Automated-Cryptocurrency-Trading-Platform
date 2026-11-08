# Phase 3C Part 4 — Development Migration Test Plan

| Field | Value |
|-------|-------|
| Date | 2026-11-06 |
| Status | **Plan ready** — execute only after identity + migration approval |
| Production | Untouched |

Distinguish clearly:

| Layer | Proves |
|-------|--------|
| Offline migration audit | File/model consistency |
| Guard unit tests | Production rejection / fail-closed identity |
| Local disposable Postgres | Full Alembic chain on throwaway DB |
| Real Supabase **development** project | Auth roles, RLS with `authenticated`, Data API settings |

**Do not** present mocked unit tests as proof of live Supabase RLS.

---

## A — After approved migrations on development

### Database assertions

- [ ] `app.alembic_version.version_num = 20261105_0003`
- [ ] Tables exist: `agent_decisions`, `system_events`, `strategy_configs`, `exchange_account_bindings`
- [ ] Catalog tables have `owner_user_id`
- [ ] Binding constraints/indexes present (active unique cred/env, telemetry scope unique)
- [ ] RLS enabled on catalog + bindings tables
- [ ] No broad `GRANT USAGE ON SCHEMA app TO anon, authenticated` beyond intended policies
- [ ] Schema `app` **not** exposed in Supabase Data API

### Ownership isolation (synthetic users only)

- [ ] Owner reads permitted owned rows (when private reads later enabled in **dev** only if separately approved)
- [ ] Wrong owner denied / empty
- [ ] Unauthenticated denied on protected paths
- [ ] `service_role` JWT rejected as end-user
- [ ] Pending / revoked bindings → inactive/denied
- [ ] Forged binding ID → `cross_tenant_forbidden`
- [ ] Wrong environment credential mismatch denied
- [ ] Telemetry scope mismatch → unavailable / denied
- [ ] Unknown `credential_ref` denied

Keep `PRIVATE_DATA_READS_ENABLED=false` unless a **separate** development experiment is approved; default remains fail-closed.

### Supabase-specific

- [ ] Dev JWT issuer/audience match development project
- [ ] No production Auth users required
- [ ] No production account bindings
- [ ] No mainnet Bybit credentials in env

---

## B — Local disposable PostgreSQL (optional)

Requirements:

- Host `127.0.0.1` / `localhost` only  
- `CRYPTONOVA_ALLOW_LOCAL_DISPOSABLE_DB=true`  
- Empty database name e.g. `cryptonova_dev_disposable`  
- Explicit cleanup confirmation  

Plan:

1. Guard with local flags  
2. `alembic upgrade 20261105_0003`  
3. Assert head + tables  
4. Optional `alembic downgrade 20261104_0001` on the same disposable DB  
5. Drop DB only after confirmation  

---

## C — Offline / CI (already automated)

```bash
uv run pytest -q tests/test_dev_database_target_guard.py
uv run python -c "from apps.api.app.migration_audit import audit_initial_migration, audit_ownership_migration, audit_exchange_binding_migration as a3; assert audit_initial_migration().ok and audit_ownership_migration().ok and a3().ok"
```

---

## Explicit non-goals

- No production migrate  
- No authenticated Bybit calls  
- No real order HTTP  
- No private SSE enable  
- No Git commit/push unless asked  
