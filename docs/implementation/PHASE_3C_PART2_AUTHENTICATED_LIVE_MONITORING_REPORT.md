# Phase 3C Part 2 — Authenticated, ownership-bound live monitoring

| Field | Value |
|-------|-------|
| Date | 2026-11-05 |
| Scope | Postgres binding repository, credential_ref resolver, JWT-gated wallet + worker snapshot, authenticated Next.js proxy, LIVE frontend wiring |
| Migration `20261104_0002` | **Not applied** (offline audit pass) |
| Migration `20261105_0003` | **Not applied** (offline audit pass) |
| `PRIVATE_DATA_READS_ENABLED` | **false** (unchanged — fail closed) |
| Private SSE | **Disabled** |
| Real order HTTP | **Disabled** |
| `OPERATOR_LOCAL_BROWSER_PROXY_ENABLED` | **false by default** (break-glass only; never auth shortcut) |
| Git commit / push | **Not performed** |

---

## 1. Audit findings (code-verified)

### Fixed in Part 2

| Finding | Remediation |
|---------|-------------|
| Binding store was in-memory only | `SqlAlchemyBindingStore` against `app.exchange_account_bindings` (requires migrated DB) |
| Owner-bound wallet returned `exchange_binding_credential_resolver_pending` | Server-only `resolve_credential_ref` → Bybit session; secrets never in responses |
| Browser proxies relied on loopback privilege or break-glass | JWT forwarded via `authenticated-proxy.ts`; break-glass only when no Bearer and env flag true |
| UUID `telemetry_scope_id` scrubbed by ledger (`len > 32`) | `_is_allowed_telemetry_scope` accepts binding UUIDs; still rejects fingerprint-like labels |

### Controls confirmed still fail-closed

| Control | Status |
|---------|--------|
| JWT verifier | Rejects `anon` / `service_role`; requires authenticated user `sub` |
| `PRIVATE_DATA_READS_ENABLED=false` | Owner-bound wallet/snapshot → `403 ownership_schema_required` |
| Operator-local diagnostic | Loopback peer only; **never** used when `Authorization` present |
| Client-supplied binding ID | Accepted only after repository ownership match |
| No auto-assignment of operator Bybit account to all users | Enrollment requires attestation; per-owner upsert only |
| SSE | Still disabled |
| Trading / order mutation HTTP | Still absent |

### Residual gaps (intentional / operator-gated)

1. Migrations `0002` / `0003` not applied to remote Postgres.
2. Production binding rows empty until operator enrollment.
3. Credential env vars (`BYBIT_*_API_KEY/SECRET`) must be provisioned per `credential_ref` allowlist.
4. Browser access token is operator/sessionStorage-assisted (`cryptonova.access_token`) until full Supabase auth UI session wiring.
5. Binding-scoped SSE not implemented (must stay off).

---

## 2. PostgreSQL binding repository

**Files**

- `apps/api/app/exchange/binding_store.py` — `InMemoryBindingStore`, `SqlAlchemyBindingStore`
- `apps/api/app/exchange/bindings.py` — domain, `enroll_operator_binding`, `require_active_binding_for_principal`
- `apps/api/app/models.py` — `ExchangeAccountBindingRow` (from Part 1)
- `apps/api/app/exchange/access.py` — dual-path context; prefers SQLAlchemy when `DATABASE_URL` configured

**Behavior**

- Operator-only enrollment with attestation; pending / active / revoked / error.
- Environment isolation: `testnet` | `mainnet` | `demo`.
- Opaque `credential_ref` only (rejects key-like strings).
- `telemetry_scope_id = str(binding.id)` (non-secret).
- Requested binding IDs verified against owner; wrong owner → `403 cross_tenant_forbidden`.
- Ambiguous multi-binding without environment → `403 exchange_binding_ambiguous`.

---

## 3. Credential resolver

**File:** `apps/api/app/exchange/credentials.py`

| `credential_ref` | Env material | Environment |
|------------------|--------------|-------------|
| `env:BYBIT_TESTNET_OPERATOR` | `BYBIT_TESTNET_API_KEY` / `SECRET` | testnet |
| `env:BYBIT_MAINNET_OPERATOR` | `BYBIT_MAINNET_API_KEY` / `SECRET` | mainnet |
| `env:BYBIT_DEMO_OPERATOR` | `BYBIT_DEMO_API_KEY` / `SECRET` | demo |
| `env:BYBIT_OPERATOR` | `BYBIT_API_KEY` / `SECRET` + process flags | derived |

Rejects: unknown ref, missing env, environment mismatch, empty keys.  
`ResolvedBybitCredentials` is in-memory only — never serialized to API, telemetry, or logs.

---

## 4. Authenticated read APIs

### Wallet — `GET /api/v1/exchange/wallet`

1. `EXCHANGE_WALLET_READS_ENABLED` required.
2. With Bearer: JWT → active binding → `PRIVATE_DATA_READS` → resolve `credential_ref` → read-only UNIFIED wallet.
3. Without Bearer: operator-local loopback diagnostic only.
4. Fail closed on missing ownership / credentials / DB.

### Worker snapshot — `GET /api/v1/observability/worker-snapshot`

1. Same dual-path authorization.
2. Owner-bound responses filtered to `binding.telemetry_scope_id`.
3. No matching events → `data_mode=unavailable` (no SAMPLE mix).
4. Orders stripped on owner path (order ownership reads deferred).

SSE `/api/v1/observability/stream` remains disabled.

---

## 5. Next.js authenticated proxy

**Files**

- `apps/web/src/lib/security/authenticated-proxy.ts`
- `apps/web/src/app/api/exchange/wallet/route.ts`
- `apps/web/src/app/api/observability/snapshot/route.ts`
- `apps/web/src/lib/security/operator-proxy-gate.ts` (Part 1)

**Rules**

- Prefer `Authorization: Bearer <user JWT>` → forward **only** that token to FastAPI.
- Never use break-glass when a Bearer token is present.
- Unauthenticated: `401 authentication_required` unless `OPERATOR_LOCAL_BROWSER_PROXY_ENABLED=true`.
- `Cache-Control: no-store`; no Bybit secrets in responses.

---

## 6. Frontend LIVE wiring

| Surface | Behavior |
|---------|----------|
| `WalletBalancePanel` | Sends `authHeaders()`; surfaces unauthorized / ownership / disabled states; no invented balances |
| Agent Studio LIVE | `useAgentSnapshot("live")` → worker proxy with Bearer; rejects fixture leak; unavailable on disconnect |
| SAMPLE | Unchanged labeled fixtures |
| REPLAY | Unchanged offline path |

Token helper: `apps/web/src/lib/auth/browser-access-token.ts` (`sessionStorage` key `cryptonova.access_token`).

---

## 7. Migration readiness

| Revision | Offline audit | Applied |
|----------|---------------|---------|
| `20261104_0001` | Pass | Assumed prior / operator |
| `20261104_0002` | Pass | **No** |
| `20261105_0003` | Pass | **No** |

Review SQL:

- `apps/api/sql/review/20261104_0002_ownership_rls.sql`
- `apps/api/sql/review/20261105_0003_exchange_account_bindings.sql`

**Operator runbook:** `docs/implementation/PHASE_3C_PART2_OPERATOR_RUNBOOK.md`

**Do not** auto-apply. Backup required. Keep `PRIVATE_DATA_READS_ENABLED=false` until enrollment + credential checks succeed.

Rollback sketch (after backup): `alembic downgrade 20261104_0001`.

---

## 8. Test results

| Command | Result |
|---------|--------|
| `uv run pytest -q` | **237 passed** |
| `apps/web npm run typecheck` | **pass** |
| `apps/web npm run lint` | **pass** (SWC native binary warning on this host; eslint clean) |
| `npx vitest run` | **15 passed** |
| `apps/web npm run build` | **pass** |

### Isolation / authorization matrix covered

- Valid owner path (with flag on in tests)
- Wrong owner / cross-tenant
- Missing binding
- Revoked binding
- Wrong environment / credential mismatch
- Invalid JWT
- `service_role` rejection
- Credential resolution failure
- Telemetry scope mismatch → unavailable, empty events
- Cross-user data isolation
- `PRIVATE_DATA_READS_ENABLED=false` fail-closed
- Next proxy JWT-forward source guards
- Operator-local without JWT still works for diagnostics
- SQLite-backed `SqlAlchemyBindingStore` enrollment persistence

---

## 9. Implemented / updated files (Part 2)

| Path | Role |
|------|------|
| `apps/api/app/exchange/binding_store.py` | Durable + in-memory repositories |
| `apps/api/app/exchange/bindings.py` | Protocol, enrollment, authz |
| `apps/api/app/exchange/credentials.py` | Server-only credential_ref resolver |
| `apps/api/app/exchange/access.py` | Dual-path + store selection |
| `apps/api/app/exchange/router.py` | Owner-bound wallet reads |
| `apps/api/app/observability/router.py` | Scope-filtered worker snapshot |
| `agent/telemetry_ledger.py` | UUID-safe telemetry scope allowlist |
| `apps/web/src/lib/security/authenticated-proxy.ts` | JWT-forwarding proxy helper |
| `apps/web/src/app/api/exchange/wallet/route.ts` | Authenticated wallet proxy |
| `apps/web/src/app/api/observability/snapshot/route.ts` | SAMPLE vs owner-bound worker |
| `apps/web/src/lib/auth/browser-access-token.ts` | Browser Bearer helper |
| `apps/web/src/components/WalletBalancePanel.tsx` | Auth + fail-closed UX |
| `apps/web/src/features/agent-studio/hooks/use-agent-snapshot.ts` | LIVE auth wiring |
| `tests/test_exchange_bindings_phase3c.py` | Part 1 + updated proxy guards |
| `tests/test_exchange_bindings_phase3c_part2.py` | Part 2 isolation suite |
| `docs/implementation/PHASE_3C_PART2_OPERATOR_RUNBOOK.md` | Manual ops steps |
| `docs/implementation/PHASE_3C_PART2_AUTHENTICATED_LIVE_MONITORING_REPORT.md` | This report |

---

## 10. Explicit operator approval steps

1. Backup database (PITR / snapshot).
2. Review review SQL for `0002` and `0003`.
3. Confirm `app` schema is **not** in Supabase Data API; no broad grants to `anon` / `authenticated` beyond RLS SELECT.
4. Manually `alembic upgrade 20261104_0002` then `20261105_0003`.
5. Provision env credentials matching allowlisted `credential_ref` values.
6. Enroll **one** owner binding with attestation; set worker `EXCHANGE_ACCOUNT_BINDING_ID`.
7. Verify owner wallet + scoped snapshot offline/staging.
8. Only then set `PRIVATE_DATA_READS_ENABLED=true`.
9. Keep `OPERATOR_LOCAL_BROWSER_PROXY_ENABLED=false` on multi-user hosts.
10. Keep SSE and order mutation HTTP disabled.

---

## 11. Known limitations

- Authenticated live monitoring is **code-ready** but **runtime-closed** until migrations, enrollment, credentials, and the private-reads flag are operator-approved.
- No public self-serve binding UI (by design).
- Owner-bound order lifecycle table still stripped from snapshot.
- Full Supabase session cookie → access-token plumbing may still need product auth UI; interim `sessionStorage` helper is documented.
- Host SWC binary warning does not block typecheck/lint/build success.

---

## 12. Next milestones (Phase 3C Part 3+)

1. Operator-approved migrate + enroll + enable private reads in a controlled environment.
2. Binding-scoped SSE design with cursor ownership proofs (still off until proven).
3. Per-tenant credential vault (beyond env allowlist) if multi-account grows.
4. Owner-bound order / fill read contracts (read-only).
5. Replace interim browser token helper with full Supabase auth session integration.
6. Expand CI against a migrated Postgres fixture (read-only).

---

## Success statement

Phase 3C Part 2 delivers ownership-verified, fail-closed read-only wallet and Agent Studio LIVE telemetry paths: durable binding repository, server-only credential resolution, JWT-gated FastAPI APIs, authenticated Next.js proxies that never treat break-glass as user auth, and frontend LIVE surfaces that do not fabricate balances or agent status. Any missing approval, migration, binding, or flag remains closed.
