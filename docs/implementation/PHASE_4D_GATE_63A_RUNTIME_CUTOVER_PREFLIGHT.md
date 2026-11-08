# Phase 4D Gate 63A — Runtime Credential Cutover Security Preflight

| Field | Value |
| --- | --- |
| Gate | **63A — PREFLIGHT ONLY** |
| Date | 2026-11-08 |
| Decision | **CONDITIONAL — REMEDIATION REQUIRED** |
| Target | `wmirifmgaftassgrfbyl` (`ap-southeast-2`) |
| Alembic | `20261108_0005` |
| Gate 62 SHA-256 | `9e0efdd317926a7ce5959f87e77c60c122e87ec62c49345597840cc6307f318a` |
| Remote mutations | **None** |
| Credential cutover | **NOT EXECUTED** |

Companions: `PHASE_4D_GATE_63A_PRIVILEGE_MATRIX.md`, `PHASE_4D_GATE_63_NON_EXECUTED_CUTOVER_RUNBOOK.md`

---

## 1. Executive summary

Gate 62 security objects are intact on the correct development project. FastAPI still connects as BYPASSRLS-capable `postgres`. Identity/JWT/pool building blocks exist in code but remain disabled (`RUNTIME_DB_IDENTITY_ENABLED` unset/false).

**Primary remediation before Gate 63:** `cryptonova_api_runtime` lacks effective `USAGE` on schema `auth` (ACL owned by `supabase_admin`; Gate 62 grant did not stick). Without that, a future LOGIN inheriting runtime may fail to resolve `auth.uid()` despite EXECUTE privilege.

**Secondary remediations:** wire fail-closed `DATABASE_RUNTIME_URL` engine selection (no privileged fallback); re-run disposable local LOGIN/RLS harness when `:55432` is available; execute live Auth isolation only under Gate 63 authorization.

Overall: **CONDITIONAL — REMEDIATION REQUIRED**. Not authorization to cut over.

---

## 2. Current remote baseline

| Check | Result | Criterion |
| --- | --- | --- |
| Project ref | `wmirifmgaftassgrfbyl` | **PASS** |
| Region host | `aws-0-ap-southeast-2.pooler.supabase.com` | **PASS** |
| PostgreSQL | **17.11** | **PASS** |
| Alembic | `20261108_0005` | **PASS** |
| Active 0005 SHA-256 | match | **PASS** |
| `cryptonova_api_runtime` | NOLOGIN NOBYPASSRLS NOSUPERUSER INHERIT | **PASS** |
| `cryptonova_migrator` | NOLOGIN NOBYPASSRLS NOSUPERUSER INHERIT | **PASS** |
| `cryptonova_api_login` | absent | expected |
| Table owners | all `postgres` | **PASS** |
| Phase 4D counts | 0×5 | **PASS** |
| Runtime DELETE grants | none | **PASS** |
| Runtime CREATE ON app | false | **PASS** |
| Runtime table grants | match Gate 62 | **PASS** |
| Runtime + authenticated policies | present / intact | **PASS** |
| Session user | `postgres`, `rolbypassrls=true` | expected pre-63 |
| `USAGE ON SCHEMA auth` (runtime) | **false** | **CONDITIONAL** |

Tools: `_gate_63a_readonly_runtime_inventory.py`, `_gate_63a_readonly_auth_schema_acl.py`, revised `_gate_c1_readonly_catalog.py`.

---

## 3. Existing privileged runtime analysis

| Area | Finding |
| --- | --- |
| Engine | `apps/api/app/db.py` → `settings.sqlalchemy_url()` from `DATABASE_URL` |
| Pool | Default QueuePool, `pool_pre_ping=True`; no checkout identity reset hook |
| Sessions | Per-request in `deps.get_db_session` / `cloud_history_router.get_cloud_repo` |
| RLS | Ineffective for current connection (BYPASSRLS) |
| App filters | Still mandatory (`cloud_repository`, owner binding) |
| GUC attach | `db_identity.attach_owner_identity` — **OFF** unless flag |
| Config stubs | `DATABASE_RUNTIME_URL` / `DATABASE_MIGRATOR_URL` fields exist; **unused** by engine |

Gap vs desired architecture: FastAPI does not yet authenticate as least-privilege LOGIN; enabling GUC alone on `postgres` does not enforce RLS.

---

## 4. Proposed dedicated LOGIN architecture

Suggested name: **`cryptonova_api_login`**

| Property | Design |
| --- | --- |
| LOGIN | Yes |
| NOSUPERUSER / NOBYPASSRLS / NOCREATEDB / NOCREATEROLE | Yes |
| INHERIT | Yes (role attribute) |
| Membership | `IN ROLE cryptonova_api_runtime` with inheriting membership (no SET ROLE in app) |
| Direct table grants | None — inherit from runtime |
| Ownership | None |
| Privileged memberships | Forbidden (`service_role`, `supabase_admin`, etc.) |

PostgreSQL inheritance: role `INHERIT` + membership inherit ⇒ grants on runtime apply to LOGIN without `SET ROLE`. **NOINHERIT** LOGIN fails closed on grants (prior disposable harness).

```sql
-- NON-EXECUTED — REQUIRES SEPARATE AUTHORIZATION
CREATE ROLE cryptonova_api_login
  LOGIN PASSWORD '<offline-secret>'
  NOSUPERUSER NOCREATEDB NOCREATEROLE NOBYPASSRLS
  INHERIT
  IN ROLE cryptonova_api_runtime;
```

Also required beforehand:

```sql
-- NON-EXECUTED — REQUIRES SEPARATE AUTHORIZATION
GRANT USAGE ON SCHEMA auth TO cryptonova_api_runtime;
```

---

## 5. Effective privilege matrix

See `PHASE_4D_GATE_63A_PRIVILEGE_MATRIX.md`.

Highlights: runtime S/I/U on signal tables; SELECT-only scheduler/catalog; no DELETE; migrator DML+CREATE; postgres BYPASSRLS residual; **auth USAGE gap**.

---

## 6. JWT verification review

Implementation: `apps/api/app/auth/jwt_verifier.py` + `deps.get_current_principal`.

| Check | Status |
| --- | --- |
| Signature | JWKS ES256/RS256 (default) or HS256 legacy | **PASS** design |
| JWKS URL / issuer | Derived from `SUPABASE_URL` or explicit settings | **PASS** |
| Algorithms allowlist | Explicit; rejects others | **PASS** |
| `iss` / `aud` / `exp` / `nbf` / `iat` / `sub` | Required in decode options | **PASS** |
| Role claim | Allows `authenticated` only; rejects `anon` / `service_role` | **PASS** |
| Missing Bearer | 401 | **PASS** |
| JWKS failure | 503 fail-closed | **PASS** |
| Token logging | Not logged | **PASS** |
| Live JWKS vs mocks | Unit/integration use doubles; live Auth **plan only** | **CONDITIONAL** |

Trust boundary: DB GUC is **not** identity proof. Only FastAPI-verified `sub` may be attached.

---

## 7. Transaction-local identity design

Flow: access token → JWT verify → `AuthenticatedPrincipal.user_id` → `attach_owner_identity` → `set_config('request.jwt.claim.sub', :sub, true)` (SET LOCAL) → RLS `auth.uid()`.

| Property | Status |
| --- | --- |
| Verified JWT only | **PASS** (router uses principal; no client owner id) |
| Bound params for GUC | **PASS** |
| Fail-closed bad UUID | **PASS** |
| Same session/transaction | Intended in `get_cloud_repo` | **PASS** design |
| Clear on finally | Best-effort | **PASS** |
| Default disabled | **PASS** |
| Catalog `get_db_session` | Does **not** attach GUC yet | gap for full cutover |
| Pooler | Session pooler required; txn pooler unsafe for SET LOCAL | document |

---

## 8. SQLAlchemy pool isolation

| Evidence | Result |
| --- | --- |
| `ConnectionIdentityGuard` checkout reset | Unit **PASS** |
| Concurrent `IdentityLeakTracker` | Unit **PASS** |
| Real engine pool + SET LOCAL leak test | **NOT VERIFIED** this session (no disposable PG) |
| Prior Gate 60 harness (PG18 :55432) | Historical PASS when cluster up |

Recommendation for Gate 63: add SQLAlchemy multi-checkout SET LOCAL isolation test on disposable PG before enabling production traffic.

---

## 9. Local PostgreSQL RLS integration results

| Item | Result |
| --- | --- |
| Disposable `:55432` this session | **Down** |
| System PostgreSQL 18 service | Running on `:5432` (password-gated; not used) |
| This-session LOGIN/RLS harness | **NOT VERIFIED** |
| Prior Option A harness (PG18) | 18/18 PASS documented in Gate 60/62 reviews |
| Offline unit tests (63A) | **19 passed, 1 skipped** (harness skip) |

Recorded version for prior evidence: **PostgreSQL 18** local vs remote **17.11** — inheritance/RLS semantics relied upon are not 18-specific.

---

## 10. Runtime secrets and configuration plan

| Topic | Plan |
| --- | --- |
| Runtime URL | `DATABASE_RUNTIME_URL` → session pooler user `cryptonova_api_login` |
| Admin/Alembic | Separate privileged URL; never used when identity mode on |
| Fail-closed | If `RUNTIME_DB_IDENTITY_ENABLED=true` and runtime URL missing/invalid → **refuse startup** (must be implemented before cutover) |
| TLS | `sslmode=require` |
| Redaction | Existing `redacted_database_url()` |
| Rotation | ALTER ROLE + secret update + process recycle |
| Passwords | Offline only; never commit |

Current gap: `sqlalchemy_url()` ignores `database_runtime_url` — **CONDITIONAL**.

---

## 11. Future cutover sequence

See `PHASE_4D_GATE_63_NON_EXECUTED_CUTOVER_RUNBOOK.md` §§4–6: authorize → remediate auth USAGE → CREATE LOGIN → store secret → wire engine → enable identity flag → health + isolation → verify.

---

## 12. Rollback plan

Privileged URL restore after a live cutover is a **security regression** requiring explicit operator approval. Prefer leave identity flag OFF and never cut over if LOGIN validation fails. Full steps in runbook §8.

---

## 13. Live Auth/RLS validation plan

Two real users A/B; verified tokens; cross-owner denial; missing/invalid/expired JWT; concurrency; RO role inspection. Synthetic remote INSERT only under separate write authorization. **Not executed in 63A.**

---

## 14. Safety flags audit

| Flag | Observed |
| --- | --- |
| `RUNTIME_DB_IDENTITY_ENABLED` | unset / false |
| Cloud writes / operator approved | unset |
| Cloud sync | unset |
| Binding persistence | unset |
| `AGENT_ALLOW_LIVE` | `false` |
| Testnet / perpetual orders | unset |
| `CRYPTONOVA_ALLOW_DEV_MIGRATIONS` | `false` |
| `PRIVATE_DATA_READS_ENABLED` | `false` |

No cutover; no flag enablement in this gate.

---

## 15. Residual risks

1. **auth schema USAGE** missing for runtime (cutover blocker until remediated).
2. Engine still privileged; BYPASSRLS until Gate 63.
3. Fail-closed runtime URL selection not implemented.
4. Disposable PG harness not re-run this session.
5. Live JWKS/Auth isolation not proven on this project.
6. Catalog routes lack GUC attach path.
7. Transaction pooler misuse would break SET LOCAL.
8. PITR/backup still NOT VERIFIED (accepted at Gate 62).

---

## 16. Decision

### **CONDITIONAL — REMEDIATION REQUIRED**

Ready for a **separate Gate 63 authorization review** only after:

1. Effective `GRANT USAGE ON SCHEMA auth TO cryptonova_api_runtime` (authorized SQL path).
2. App fail-closed runtime URL wiring (local code) + tests.
3. Optional: disposable local LOGIN harness re-PASS.

This document is **not** Gate 63 execution approval.

---

## 17. Explicit non-execution attestation

Gate 63A performed no remote CREATE/ALTER ROLE, GRANT/REVOKE (beyond read-only inspection), POLICY changes, DML, Alembic changes, LOGIN creation, credential rotation, FastAPI identity enablement, cloud writes, sync, historical import, exchange orders, deployment, or git push.

Local-only code change: revised `_gate_c1_readonly_catalog.py` to expect Alembic `20261108_0005` and verify 0005 checksum (Task L). Added RO scripts `_gate_63a_readonly_runtime_inventory.py`, `_gate_63a_readonly_auth_schema_acl.py`.

---

## 18. Acceptance criteria summary

| # | Criterion | Result |
| --- | --- | --- |
| 1 | Correct project | **PASS** |
| 2 | Correct Alembic | **PASS** |
| 3 | Gate 62 roles intact | **PASS** |
| 4 | Runtime NOBYPASSRLS | **PASS** |
| 5 | Dedicated LOGIN inheritance design | **PASS** (design; remote LOGIN absent) |
| 6 | Effective privileges | **CONDITIONAL** (auth USAGE gap) |
| 7 | JWT verification | **PASS** (code); live **CONDITIONAL** |
| 8 | Transaction-local identity | **PASS** (design/tests); flag OFF |
| 9 | Connection-pool isolation | **PASS** (sim); real PG **NOT VERIFIED** |
| 10 | Local PG 17 integration | **NOT VERIFIED** (prior PG18 PASS) |
| 11 | Runtime secret management | **CONDITIONAL** |
| 12 | Fail-closed startup design | **CONDITIONAL** |
| 13 | Cutover rollback readiness | **PASS** (documented) |
| 14 | Live Auth/RLS plan | **PASS** (plan only) |
| 15 | Safety flags | **PASS** |
| 16 | No remote mutations | **PASS** |
| 17 | No credential cutover | **PASS** |
| 18 | No exchange orders | **PASS** |
