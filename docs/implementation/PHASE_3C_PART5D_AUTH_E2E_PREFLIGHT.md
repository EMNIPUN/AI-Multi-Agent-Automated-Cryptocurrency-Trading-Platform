# Phase 3C Part 5D — Auth E2E Preflight

| Field | Value |
|-------|-------|
| Date | 2026-11-06 |
| Development project | `wmirifmgaftassgrfbyl` |
| Alembic | `20261105_0003` |
| Class C RLS | PASS (rolled back) |
| Auth users created this phase | **None** |
| Cloud writes | **None** |
| Git commit/push | **None** |

---

## 1. Trust path (inspected)

```
Browser
  createBrowserSupabase(NEXT_PUBLIC_URL + publishable key)
  supabase.auth.getSession() → access_token
  authHeaders() → Authorization: Bearer <user JWT>
       │
       ▼
Next.js /api/exchange/wallet | /api/observability/*
  authenticated-proxy: forward Bearer only
  break-glass OFF → 401 if no token
       │
       ▼
FastAPI
  JWKS verify (ES256/RS256) · iss/aud/exp · reject anon/service_role
  get_current_principal / resolve_exchange_read_context
  ownership + binding authz · PRIVATE_DATA_READS kill switch
       │
       ▼
Postgres (postgres BYPASSRLS) — app WHERE filters primary
  RLS Class C proven separately for role authenticated
```

---

## 2. Component status

| Component | Status | Notes |
|-----------|--------|-------|
| Browser Supabase client | Ready | Publishable key configured; URL matches dev project |
| Session establish/refresh | Ready (SDK) | `persistSession` + `autoRefreshToken` enabled |
| In-app sign-in UI | **Ready** | `/login` `/signup` `/forgot-password` `/reset-password` + shell logout |
| Token resolution | Ready | Auth session only when public env set; no sessionStorage bypass |
| Next.js proxy | Ready | Bearer forward; break-glass disabled |
| FastAPI JWKS | Ready | Issuer derived from `SUPABASE_URL`; audience `authenticated` |
| Service-role rejection | Ready | Offline proven |
| Ownership / bindings | Ready | Offline proven; live private reads still gated |
| Wallet SAMPLE fallback | Ready | 401/403 → disabled UI; no invented balances |
| Operator break-glass | Disabled | `OPERATOR_LOCAL_BROWSER_PROXY_ENABLED=false` |

---

## 3. Authentication vs authorization

| Outcome | Meaning in Part 5D |
|---------|-------------------|
| Auth success | Valid user JWT accepted by FastAPI (`/api/v1/me` 200) |
| Auth failure | 401 missing/invalid/expired/wrong-iss/service_role |
| Authz blocked (expected) | 403 `ownership_schema_required` while `PRIVATE_DATA_READS_ENABLED=false` |
| Authz success (out of scope) | Active binding + private reads enabled — **not** this phase |

Do not claim private LIVE wallet success while the kill switch is off.

---

## 4. Configuration checklist (already set)

| Key | Expected |
|-----|----------|
| API `SUPABASE_URL` | `https://wmirifmgaftassgrfbyl.supabase.co` |
| API `AUTH_JWT_MODE` | `jwks` |
| API `PRIVATE_DATA_READS_ENABLED` | `false` |
| Web `NEXT_PUBLIC_SUPABASE_URL` | same project |
| Web publishable key | `sb_publishable_…` |
| Web break-glass | `false` |
| Supabase Auth redirect allowlist | `http://localhost:3000/**` (operator must confirm in Dashboard) |

---

## 5. Gap for Class D execution

1. No disposable Auth users yet (requires approval).
2. No first-party sign-in page — use approved scripted password/magic-link sign-in or Dashboard.
3. Auth redirect URLs must include local Next origin.
4. Binding rows for cross-user denial under private reads remain optional for kill-switch tests; full binding matrix needs approved synthetic bindings **or** in-memory store overrides in API tests (preferred offline).

---

## 6. Readiness verdict

| Item | Result |
|------|--------|
| Auth architecture | **PASS** (code + env wired) |
| Real Auth E2E readiness | **UI ready; cloud blocked on manual signup approval (no service-role required)** |
| Full security gate | **NOT PASS** until Class D executes |
