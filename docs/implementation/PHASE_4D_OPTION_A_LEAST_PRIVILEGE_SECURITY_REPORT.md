# Phase 4D Option A — Least-Privilege Security Architecture Report

| Field | Value |
| --- | --- |
| Prompt | 59 — Option A local preparation |
| Date | 2026-11-07 |
| Project | `wmirifmgaftassgrfbyl` |
| Remote security changes | **NOT EXECUTED** |
| Overall status | **READY FOR SEPARATE REMOTE SECURITY-CHANGE APPROVAL** |

---

## 1. Executive summary

CryptoNova’s FastAPI process still connects as Supabase role `postgres` with **`rolbypassrls=true`**. Application-layer owner filters and dual write gates reduce risk but do **not** provide database-enforced tenant isolation.

Option A prepares a least-privilege design:

- Runtime role `cryptonova_api_runtime` (`NOSUPERUSER`, `NOBYPASSRLS`, non-owner)
- Migrator role `cryptonova_migrator` (separate credentials)
- Transaction-local JWT `sub` propagation helpers (**disabled by default**)
- Pending migration draft under `alembic/versions_proposed/` (not active)
- Offline identity/pool/gate tests; disposable Postgres RLS E2E **NOT RUN** (Docker unavailable)

**No remote roles, grants, policies, migrations, cloud writes, or exchange orders were executed.**

---

## 2. Current architecture inventory

| Consumer | DB credential today | Needs identity | Notes |
| --- | --- | --- | --- |
| Authenticated cloud history GET | `DATABASE_URL` → `postgres` | JWT `sub` | App filters; RLS bypassed |
| Catalog / bindings reads | same | JWT `sub` | Persistence OFF |
| Cloud signal write (future) | same | JWT/`SIGNAL_CLOUD_OWNER_USER_ID` | Gates OFF |
| Cloud sync worker | same (if started) | env owner UUID | Not auto-started |
| Alembic migrator | same URL historically | N/A | Must split to migrator URL |
| Public market data | none / no owner tables | N/A | Independent |
| SQLite signal SoT | local file | N/A | Operational authority |
| Operator local scripts | often same `DATABASE_URL` | operator care | Prefer RO for audits |

**Conclusion:** A single privileged credential is **not** appropriate for all consumers. Runtime vs migrator must split; workers need explicit trusted identity.

---

## 3. Existing BYPASSRLS exposure

| Fact | Evidence |
| --- | --- |
| Session user | `postgres` |
| `rolbypassrls` | `true` |
| `rolsuper` | `false` |
| Table owner (all `app.*`) | `postgres` |
| FORCE RLS | `false` on all app tables |
| Phase 4D policies | `TO authenticated` SELECT-only via `auth.uid()` |

While the connection is table owner **or** BYPASSRLS, RLS policies do not constrain FastAPI. SELECT-own policies protect Supabase Data API `authenticated` role paths, not the current API pool.

---

## 4. Role separation design

### `cryptonova_api_runtime`

| Attribute | Value | Why |
| --- | --- | --- |
| SUPERUSER | NO | Prevent privilege escalation |
| BYPASSRLS | NO | Enforce RLS |
| CREATEDB / CREATEROLE | NO | No DDL/admin |
| Table ownership | Must **not** own `app` tables | Table owners bypass RLS unless FORCE |
| Schema | `USAGE` on `app` only | Least privilege |
| Signal tables | `SELECT, INSERT, UPDATE` | Read history + future gated writes |
| DELETE | **Not granted** by default | Cleanup is separate approval |
| Catalog tables | `SELECT` only initially | Binding persistence remains OFF |
| Sequences | USAGE if UUID defaults need it | Only if required after dry-run |

### `cryptonova_migrator`

| Attribute | Value | Why |
| --- | --- | --- |
| Separate LOGIN secret | Yes | Never used by request path |
| DDL | As needed for Alembic | Controlled by `CRYPTONOVA_ALLOW_DEV_MIGRATIONS` |
| Not in FastAPI pool | Mandatory | Prevents accidental DDL from API |

### Supabase-managed roles

Do not alter `postgres` / `authenticator` / `authenticated` / `anon` beyond additive policies/grants for the new runtime role. Existing `authenticated` SELECT policies remain for Data API defense-in-depth.

---

## 5. RLS policy audit

| Table | RLS | FORCE | Owner | Policies today | Gap for runtime writes |
| --- | --- | --- | --- | --- | --- |
| `signal_history` | ON | OFF | postgres | SELECT → `authenticated` | Need SELECT/INSERT/UPDATE → `cryptonova_api_runtime`; no DELETE |
| `signal_agent_contributions` | ON | OFF | postgres | SELECT → authenticated | same |
| `signal_risk_events` | ON | OFF | postgres | SELECT → authenticated | same |
| `scheduler_*` | ON | OFF | postgres | SELECT → authenticated | same; grant writes only when Gate D/E needs |
| `exchange_account_bindings` | ON | OFF | postgres | SELECT active own → authenticated | SELECT for runtime; INSERT only if persistence gate |
| Catalog (`agent_decisions`, etc.) | ON | OFF | postgres | SELECT → authenticated | SELECT for runtime |

**Critical:** SELECT-own policies are **not** sufficient for INSERT/UPDATE. Missing write policies would cause fail-closed denials once the runtime role is subject to RLS — which is correct until policies are added in the approved migration.

`USING` vs `WITH CHECK`: SELECT/UPDATE USING for visibility; INSERT/UPDATE WITH CHECK to prevent writing foreign `owner_user_id`.

---

## 6. Identity propagation design

```text
Supabase access JWT
  → JWKS/HS256 verifier (iss/aud/exp/nbf/role/sub)
  → AuthenticatedPrincipal.user_id
  → UUID validate
  → SQLAlchemy session BEGIN
  → set_config('request.jwt.claim.sub', sub, true)  -- SET LOCAL
  → repository queries still filter owner_user_id  -- defense in depth
  → RLS auth.uid() aligns with GUC for runtime role
  → COMMIT / ROLLBACK drops SET LOCAL
  → pool checkout resets any residual state
```

**Trust boundary:** A role that can `SET` the GUC can impersonate. Controls:

1. Runtime role has no SQL injection / ad-hoc SQL endpoint.
2. Only server-side FastAPI attaches after JWT verify.
3. Prefer **dedicated runtime credentials** over `SET ROLE` from `postgres` (SET ROLE alone does not remove privileged password from the app).
4. Application owner filters retained forever.

Local helpers: `apps/api/app/security/db_identity.py`, `session_identity.py`. Flag: `RUNTIME_DB_IDENTITY_ENABLED` default **false**.

---

## 7. SQLAlchemy connection safety

| Topic | Status |
| --- | --- |
| Engine | `create_engine` + `pool_pre_ping`, no URL logging |
| Session | `autoflush=False`, commit/rollback in routers |
| Identity attach | Optional in `cloud_history_router.get_cloud_repo` |
| Pool leak model | `ConnectionIdentityGuard` checkout reset — offline tested |
| Nested TX | SET LOCAL scoped to transaction — document caution with SAVEPOINT |
| Background worker | Must pass explicit owner; no ambient GUC inheritance |

---

## 8. Phase 3C compatibility

- Binding persistence remains dual-gated OFF.
- Runtime needs SELECT on `exchange_account_bindings` for owner-bound reads when private reads enabled.
- Do **not** grant INSERT/UPDATE on bindings until a dedicated persistence security review.
- In-memory fixture store continues for default API operation.

---

## 9. Phase 4D compatibility

- Cloud repository retains owner filters + write gates.
- `require_gates=False` remains test-only.
- No HTTP cloud write endpoint.
- Sync worker not started by lifespan.
- Payload `4D.1.0` execution invariants unchanged.

---

## 10. Threat model (abbreviated)

| Threat | Mitigation |
| --- | --- |
| Cross-tenant SELECT via API bug | App filter + RLS (after Option A remote) |
| Privileged credential theft | Separate runtime secret; rotate; no BYPASSRLS |
| GUC impersonation | No client SQL; trusted attach only |
| Accidental sync/write | Dual gates OFF |
| Migrator misuse | Separate URL; migrations gated |
| Exchange orders | Live flags OFF; out of scope |

---

## 11. Remaining risks

1. Remote Option A not applied — BYPASSRLS remains until approved gate.
2. Disposable Postgres RLS E2E **NOT RUN** (no Docker here).
3. Supabase may require dashboard/SQL editor steps for LOGIN role passwords.
4. FORCE RLS not proposed by default (table-owner edge cases) — optional later hardening.
5. `SET ROLE` from postgres is **insufficient** as the sole control.

---

## 12. GO / NO-GO

### **READY FOR SEPARATE REMOTE SECURITY-CHANGE APPROVAL**

Local design, pending migration artifact, and offline tests are sufficient to request a separate remote security-change gate. This does **not** authorize applying roles/grants/policies or switching production credentials.

---

## Acceptance criteria (Prompt 59)

| # | Criterion | Result |
| --- | --- | --- |
| 1 | Runtime-role architecture documented | **PASS** |
| 2 | RLS policies reviewed | **PASS** |
| 3 | Missing write policies identified | **PASS** |
| 4 | JWT→DB identity design documented | **PASS** |
| 5 | SQLAlchemy TX identity locally tested | **PASS** (offline) |
| 6 | No unintended pool identity leakage | **PASS** (mocked) |
| 7 | Phase 3C compatibility reviewed | **PASS** |
| 8 | Phase 4D compatibility reviewed | **PASS** |
| 9 | Local role/RLS tests if PG available | **NOT VERIFIED** / NOT RUN |
| 10–12 | Python / frontend / tsc | See test report |
| 13–14 | Migration + recovery plans | **PASS** (docs) |
| 15–18 | Gates/orders OFF | **PASS** |
| 19–20 | No remote change / no push | **PASS** |
| Remote enforcement live | **NOT VERIFIED** |
