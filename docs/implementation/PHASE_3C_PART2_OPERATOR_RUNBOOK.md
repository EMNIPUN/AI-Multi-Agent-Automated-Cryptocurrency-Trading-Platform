# Phase 3C Part 2 — Operator migration & enrollment runbook

**DO NOT auto-apply.** Operator approval required for every step.
`PRIVATE_DATA_READS_ENABLED` must remain `false` until steps 1–6 succeed.

## Prerequisites

- Database backup completed (Supabase PITR / snapshot).
- Review SQL:
  - `apps/api/sql/review/20261104_0002_ownership_rls.sql`
  - `apps/api/sql/review/20261105_0003_exchange_account_bindings.sql`
- Confirm schema `app` is **not** exposed in Supabase Data API.
- Confirm no broad `GRANT USAGE ON SCHEMA app TO anon, authenticated`.

## 1) Offline audit (safe)

```bash
uv run python -c "from apps.api.app.migration_audit import audit_initial_migration, audit_ownership_migration, audit_exchange_binding_migration as a3; print(audit_initial_migration()); print(audit_ownership_migration()); print(a3())"
```

## 2) Apply migrations (manual only)

From repo root, with `DATABASE_URL` set in a **server-side** env (never commit secrets):

```bash
# Backup first.
cd apps/api
alembic upgrade 20261104_0002
alembic upgrade 20261105_0003
alembic current
```

Rollback plan (only if needed, after backup):

```bash
alembic downgrade 20261104_0001
```

## 3) Provision credential_ref material

Map opaque refs to env vars (examples):

| credential_ref | Required env vars | Environment |
|----------------|-------------------|-------------|
| `env:BYBIT_TESTNET_OPERATOR` | `BYBIT_TESTNET_API_KEY`, `BYBIT_TESTNET_API_SECRET` | testnet |
| `env:BYBIT_MAINNET_OPERATOR` | `BYBIT_MAINNET_API_KEY`, `BYBIT_MAINNET_API_SECRET` | mainnet |
| `env:BYBIT_DEMO_OPERATOR` | `BYBIT_DEMO_API_KEY`, `BYBIT_DEMO_API_SECRET` | demo |
| `env:BYBIT_OPERATOR` | `BYBIT_API_KEY`, `BYBIT_API_SECRET` + `BYBIT_TESTNET`/`BYBIT_DEMO` flags | derived |

Never put raw keys into the bindings table.

## 4) Enroll one owner binding (operator-attested)

Use a one-off operator script / admin session against Postgres — do **not** auto-assign to all users.

Required fields:

- `owner_user_id` = verified Supabase Auth UUID
- `provider` = `bybit`
- `environment` = `testnet` | `mainnet` | `demo`
- `credential_ref` from allowlist above
- `enrollment_attestation` = ticket / change record
- `status` = `pending` until reviewed, then `active`
- `telemetry_scope_id` = binding UUID (non-secret)

Set worker:

```bash
EXCHANGE_ACCOUNT_BINDING_ID=<binding-uuid>
```

## 5) Enable private reads (last)

Only after bindings + credentials verified:

```bash
PRIVATE_DATA_READS_ENABLED=true
```

Keep:

```bash
OBSERVABILITY_LIVE_STREAM_ENABLED=false
OPERATOR_LOCAL_BROWSER_PROXY_ENABLED=false   # multi-user / hosted
```

## 6) Browser access

Browser calls Next.js with:

```http
Authorization: Bearer <Supabase user access token>
```

Next forwards JWT to FastAPI. Operator-local break-glass must stay off in multi-user deploys.

## 7) Verification checklist

- [ ] Owner wallet 200 with own binding
- [ ] Wrong user 403
- [ ] Revoked binding 403
- [ ] Wrong environment 403
- [ ] Missing JWT 401 on proxy
- [ ] LIVE worker snapshot scoped to `telemetry_scope_id`
- [ ] SAMPLE path unchanged
- [ ] No secrets in responses/logs
- [ ] SSE still disabled
- [ ] No order mutation routes
