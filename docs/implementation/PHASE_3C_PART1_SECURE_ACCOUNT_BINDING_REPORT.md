# Phase 3C Part 1 — Secure exchange-account binding foundation

| Field | Value |
|-------|-------|
| Date | 2026-11-05 |
| Scope | Ownership model, proxy hardening, migration prep, fail-closed authorized-read architecture |
| Migration `20261104_0002` | **Not applied** (offline audit only) |
| Migration `20261105_0003` | **Prepared only — not applied** |
| `PRIVATE_DATA_READS_ENABLED` | **false** (unchanged) |
| Private SSE | **Disabled** |
| Real trading HTTP | **Disabled** |
| Git commit / push | **Not performed** |

---

## 1. Security audit findings

### Critical: Next.js same-origin proxy privilege bridge (fixed)

**Finding.** FastAPI operator-local diagnostics correctly require a loopback TCP peer and reject `Authorization` / forwarded headers. However, the Next.js server process fetching `http://127.0.0.1:8000/...` **is** a loopback peer. Therefore any external browser calling:

- `/api/exchange/wallet`
- `/api/observability/snapshot?source=worker`

could previously receive the operator Bybit wallet / worker telemetry without user ownership proof.

Host / Origin / CORS / “localhost in the URL” were **never** sufficient authorization on FastAPI — but the Next.js hop turned loopback into a multi-user gateway.

**Remediation (Part 1).** Privileged Next.js proxies are **fail-closed by default**. They refuse unless `OPERATOR_LOCAL_BROWSER_PROXY_ENABLED=true` (explicit single-operator break-glass). Authenticated ownership-bound browser reads remain deferred to Part 2.

### Other controls reviewed

| Control | Status |
|---------|--------|
| Supabase JWT verifier | Rejects `anon` / `service_role`; requires `authenticated` + `sub` |
| Catalog ownership (`owner_user_id`) | Application filters primary; RLS defense in depth |
| Operator-local gate | TCP peer + loopback bind; Host header not trusted |
| `PRIVATE_DATA_READS_ENABLED` | Still false; catalog + owner-bound exchange paths deny |
| Migration 0002 | Adds catalog ownership columns only — **not** exchange-account binding |

---

## 2. Existing proxy risks (post-fix)

| Route | Default browser behavior |
|-------|--------------------------|
| `apps/web/.../api/exchange/wallet` | **403** `exchange_wallet_browser_access_requires_binding` |
| `apps/web/.../api/observability/snapshot?source=worker` | **unavailable** snapshot (no SAMPLE mix) |
| `source=sample` | Labeled fixtures only |
| Break-glass env | `OPERATOR_LOCAL_BROWSER_PROXY_ENABLED=true` — single-operator local only |

FastAPI loopback diagnostics remain available to trusted local processes (curl / operator tooling) without JWT.

---

## 3. Exchange account ownership schema

**Important:** Migration `20261104_0002` does **not** create exchange-account ownership. Part 1 adds a separate table.

### `app.exchange_account_bindings`

| Column | Purpose |
|--------|---------|
| `id` | Internal binding UUID |
| `owner_user_id` | Verified Supabase Auth user (`JWT sub`) |
| `organization_id` | Optional future org ownership (nullable) |
| `provider` | `bybit` only (check constraint) |
| `environment` | `testnet` / `mainnet` / `demo` |
| `status` | `pending` / `active` / `revoked` / `error` |
| `display_label` | Non-secret UI label |
| `credential_ref` | Opaque server pointer (e.g. `env:BYBIT_TESTNET_OPERATOR`) — **never raw keys** |
| `telemetry_scope_id` | Non-secret scope stamped on worker events (= binding id) |
| `enrollment_attestation` | Required operator attestation text |
| `enrolled_by_operator` | True for operator-attested enrollment |
| `created_at` / `updated_at` | Timestamps |

Constraints / indexes:

- Unique active `(provider, credential_ref)`
- Unique active `(owner_user_id, provider, environment)`
- Unique `telemetry_scope_id`
- RLS: `authenticated` SELECT own **active** rows only (no INSERT/UPDATE/DELETE via Data API)

### Operator enrollment procedure (safe)

1. Identify the single Supabase user UUID that should own the existing Bybit account.
2. Choose opaque `credential_ref` pointing at server env / secret store (not the key material).
3. Call `enroll_operator_binding(...)` with a non-empty attestation (ticket / change record).
4. Leave status `pending` until reviewed; set `activate=True` only after attestation review.
5. Configure worker `EXCHANGE_ACCOUNT_BINDING_ID=<binding uuid>` so telemetry is scoped.
6. **Do not** assign the operator account to every authenticated user.
7. **Do not** accept client-supplied account fingerprints or binding IDs as proof without repository ownership checks.

In-memory enrollment + authorization: `apps/api/app/exchange/bindings.py` (PostgreSQL persistence after operator applies `0003`).

---

## 4. New files and migrations

| Path | Role |
|------|------|
| `apps/api/alembic/versions/20261105_0003_exchange_account_bindings.py` | Migration (not applied) |
| `apps/api/sql/review/20261105_0003_exchange_account_bindings.sql` | Review artifact |
| `apps/api/app/models.py` | `ExchangeAccountBindingRow` |
| `apps/api/app/exchange/bindings.py` | Domain, enrollment, authz |
| `apps/api/app/exchange/access.py` | Dual-path read context |
| `apps/web/src/lib/security/operator-proxy-gate.ts` | Fail-closed Next proxy gate |
| `tests/test_exchange_bindings_phase3c.py` | Offline ownership tests |

Updated: exchange/observability routers, Next wallet/snapshot proxies, runner telemetry scope, migration audit, `.env.example`.

---

## 5. API authorization architecture

```text
Request to /wallet or /worker-snapshot
  ├─ Authorization present?
  │    ├─ Verify JWT (reject service_role / forged)
  │    ├─ Require PRIVATE_DATA_READS_ENABLED
  │    ├─ Resolve active binding for principal (never trust client id alone)
  │    ├─ Wallet: 403 exchange_binding_credential_resolver_pending (Part 2)
  │    └─ Worker: filter events to binding.telemetry_scope_id
  └─ No Authorization
       └─ assert_operator_local_diagnostic (loopback only)
```

Rules:

- JWT never falls through to operator-local.
- Missing binding / wrong user / wrong environment / inactive → **403**.
- Cross-user telemetry → empty/unavailable after scope filter (or deny before).
- SSE remains disabled.
- SQLite execution / risk authority untouched.

---

## 6. Observability ownership

- Worker stamps `account_scope_label` from `EXCHANGE_ACCOUNT_BINDING_ID` (non-secret).
- Never stamps raw `account_fp` / API keys into events.
- Owner-bound snapshot reads filter to the verified telemetry scope.
- Historical events without matching scope do not leak across accounts.
- SSE cursor remains disabled; when enabled later it must be binding-scoped.

---

## 7. Migration readiness (pre-flight — read only)

| Revision | Offline audit |
|----------|---------------|
| `20261104_0001` | Pass |
| `20261104_0002` | Pass — catalog `owner_user_id` + RLS |
| `20261105_0003` | Pass — exchange bindings prepared |

**Not run:** Alembic upgrade / downgrade / stamp / remote writes.

`PRIVATE_DATA_READS_ENABLED` remains **false**.

---

## 8. Test results

| Command | Result |
|---------|--------|
| `uv run pytest -q` | **229 passed** |
| `apps/web npm run typecheck` | **pass** (after ProcessEnv typing fix) |
| `apps/web npm run lint` | **pass** |
| Vitest agent-studio + security gate | **11 passed** |
| `apps/web npm run build` | **pass** |

Covered: operator enrollment, missing/wrong user/env, pending binding, forged JWT, service_role rejection, cross-user wallet/telemetry denial, Next proxy fail-closed source guard, operator-local transport still works without JWT, migration audits.

---

## 9. Remaining blockers

1. Migration `0002` and `0003` not applied to Supabase.
2. No PostgreSQL-backed binding repository wired to production DB yet (in-memory for tests / process state).
3. Credential resolver for owner-bound wallet reads not implemented (intentionally 403).
4. `PRIVATE_DATA_READS_ENABLED` must stay false until operator approval.
5. Browser LIVE Studio / wallet remain unavailable without break-glass or Part 2.
6. Per-user Bybit credentials still not provisioned — operator-local keys only.

---

## 10. Explicit operator approval steps

Before enabling authenticated browser private reads:

1. Review SQL: `apps/api/sql/review/20261104_0002_ownership_rls.sql` and `.../20261105_0003_exchange_account_bindings.sql`.
2. Apply Alembic `0002` then `0003` in a controlled environment (manual ops — not this session).
3. Confirm `app` schema is **not** exposed in Supabase Data API.
4. Enroll **one** operator user binding with attestation; set worker `EXCHANGE_ACCOUNT_BINDING_ID`.
5. Implement and test credential resolver (Part 2) against the binding’s `credential_ref`.
6. Only then consider `PRIVATE_DATA_READS_ENABLED=true` behind monitoring.
7. Keep `OPERATOR_LOCAL_BROWSER_PROXY_ENABLED` false in any multi-user deploy.
8. Keep SSE and trading mutation HTTP disabled until ownership proofs + audit logging ship.

---

## 11. Recommended Phase 3C Part 2

1. Persist bindings via SQLAlchemy session against Postgres (post-migration).
2. Operator enrollment CLI / admin-only path (still no public self-serve binding).
3. Credential resolver mapping `credential_ref` → server secret material.
4. Authenticated Next.js proxy that forwards **user JWT** to FastAPI (never loopback break-glass).
5. Owner-bound wallet + worker-snapshot browser UX for the enrolled user only.
6. Binding-scoped SSE design (still off until proven).
7. Expand isolation tests against a real migrated database snapshot (read-only CI where possible).

---

## Success statement

Phase 3C Part 1 delivers a secure, offline-tested exchange-account ownership foundation and closes the Next.js proxy privilege bridge. Authenticated users cannot yet read another user’s (or the operator’s) wallet/telemetry through the public app surface; future Part 2 can enable correct owner-bound read-only access only after migrations, enrollment, and credential resolution are operator-approved.
