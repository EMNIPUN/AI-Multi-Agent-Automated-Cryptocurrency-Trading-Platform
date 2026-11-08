# Phase 3C Part 5 — Auth Integration Report

| Field | Value |
|-------|-------|
| Date | 2026-11-06 |
| Development project | `wmirifmgaftassgrfbyl` |
| Scope | Supabase Auth wiring, JWT verification, Next.js session, binding authz |
| Secrets printed | **None** |

---

## 1. Intended development Auth topology

| Component | Expected development value |
|-----------|----------------------------|
| Project URL | `https://wmirifmgaftassgrfbyl.supabase.co` |
| Issuer | `https://wmirifmgaftassgrfbyl.supabase.co/auth/v1` |
| Audience | `authenticated` |
| JWKS | `…/auth/v1/.well-known/jwks.json` |
| Mode | `AUTH_JWT_MODE=jwks` (ES256/RS256 only) |
| Frontend | `NEXT_PUBLIC_SUPABASE_URL` + `NEXT_PUBLIC_SUPABASE_ANON_KEY` only |
| Private reads | `PRIVATE_DATA_READS_ENABLED=false` until separate Gate F |

Production Auth must use a **different** project URL/issuer; future prod refs go in `CRYPTONOVA_PROD_PROJECT_REFS`.

---

## 2. Verified code behavior

### FastAPI (`apps/api/app/auth/jwt_verifier.py`, `deps.py`)

| Check | Result |
|-------|--------|
| Signature verification | Required |
| `exp` / `nbf` / `iat` | Required |
| Issuer + audience | Required |
| Algorithms (JWKS) | ES256, RS256 allowlist |
| `anon` / `service_role` | Rejected (`non_user_token`) |
| Missing Bearer | `401 missing_authorization` |
| JWKS cache | `PyJWKClient(cache_keys=True)` |
| Fail closed on JWKS errors | `AuthConfigError` → 503 |

### Next.js

| Path | Behavior |
|------|----------|
| `lib/supabase/client.ts` | Browser client from public URL + anon only |
| `lib/auth/browser-access-token.ts` | Prefer `supabase.auth.getSession()`; interim sessionStorage fallback |
| `lib/security/authenticated-proxy.ts` | Forward Bearer; else 401 unless break-glass |
| `lib/security/operator-proxy-gate.ts` | Explicit env flag only |

### Exchange binding authorization (`exchange/bindings.py`, `access.py`)

| Check | Result |
|-------|--------|
| Owner must match JWT `sub` | Enforced |
| Pending / revoked | `exchange_binding_inactive` |
| Forged binding id | `exchange_binding_not_found` / cross-tenant |
| Env mismatch | `exchange_environment_mismatch` |
| Telemetry scope | Must equal binding scope |
| Credential resolution | Allowlisted refs only; no client-controlled env names |
| Private reads off | `ownership_schema_required` |

---

## 3. Live configuration evidence

| Setting | Observed |
|---------|----------|
| Project JWKS (public) | **Reachable** — 1× ES256 EC key |
| Root `.env` `SUPABASE_URL` | **Missing** |
| Root `.env` `AUTH_JWT_MODE` | **Missing** (defaults to jwks in code) |
| Root `.env` JWT secret | Absent (appropriate for JWKS) |
| `apps/web/.env.local` Supabase public vars | **Missing** |
| `apps/web/.env.local` proxy | `API_INTERNAL_BASE_URL` set; operator break-glass flag present |
| `PRIVATE_DATA_READS_ENABLED` | Unset → **false** |
| `AGENT_ALLOW_LIVE` | false |
| Service-role key in env files inspected | **Not present** as named service-role var |

**Verdict:** Cryptographic infrastructure for the development project is healthy (JWKS). **Runtime env is not yet bound** to that project for API or Next.js Auth sessions.

---

## 4. Integration test matrix (status)

| Case | Layer | Status |
|------|-------|--------|
| Missing session / Authorization | Next + FastAPI | Offline PASS |
| Expired token | FastAPI JWT | Offline PASS |
| Wrong-project issuer | FastAPI JWT | Offline PASS |
| Invalid signature | FastAPI JWT | Offline PASS |
| Cross-user resource | FastAPI ownership/bindings | Offline PASS |
| Privileged proxy without break-glass | Next proxy | Code review PASS; FE gate tests PASS |
| Missing / inactive binding | Bindings | Offline PASS |
| Unavailable private data | Kill switch | Offline PASS (`ownership_schema_required`) |
| Live wrong-project JWT against real JWKS | E2E | **Not run** (env unwired; no Auth users) |
| Sample wallet substitution | — | **Not done** (forbidden) |

---

## 5. Data API exposure checklist (operator)

In Supabase Dashboard → Project `wmirifmgaftassgrfbyl` → **Settings → API → Data API Settings** (or Project Settings → API):

- [ ] Exposed schemas list shown
- [ ] Schema `app` is **not** listed
- [ ] Only intended schemas (e.g. `public`, `graphql_public`) remain exposed
- [ ] Screenshot saved locally **without** service-role key visible

**Programmatic result:** PENDING  
**Do not change** Data API settings during this phase.

---

## 6. Residual risks

1. Until `SUPABASE_URL` is set, FastAPI JWKS verifier cannot validate real user tokens in this environment.
2. Until Next public Supabase env is set, browser Auth session path is inactive; interim sessionStorage tokens are an operator fallback only.
3. Operator-local break-glass remains a single-operator diagnostic — not multi-user auth.
4. API DB role bypasses RLS; Auth JWT isolation must not be confused with PostgreSQL RLS.

---

## 7. Recommended next configuration (no secrets in git)

API (development only):

```
SUPABASE_URL=https://wmirifmgaftassgrfbyl.supabase.co
AUTH_JWT_MODE=jwks
SUPABASE_JWT_AUDIENCE=authenticated
PRIVATE_DATA_READS_ENABLED=false
```

Web (development only):

```
NEXT_PUBLIC_SUPABASE_URL=https://wmirifmgaftassgrfbyl.supabase.co
NEXT_PUBLIC_SUPABASE_ANON_KEY=<dev anon key>
OPERATOR_LOCAL_BROWSER_PROXY_ENABLED=false
```

Do not commit filled env files. Do not enable private reads here.
