# Phase 3C Part 5B — Development Auth Configuration Report

| Field | Value |
|-------|-------|
| Date | 2026-11-06 |
| Development project | `wmirifmgaftassgrfbyl` |
| Secrets printed | **None** |
| Git commit/push | **None** |

---

## 1. Environment loading paths

### FastAPI

| Mechanism | Detail |
|-----------|--------|
| Settings class | `apps/api/app/config.py` → `ApiSettings` |
| File load | `model_config.env_file=".env"` (cwd-relative; API started from **repo root**) |
| Auth fields | `SUPABASE_URL`, `AUTH_JWT_MODE`, `SUPABASE_JWT_AUDIENCE`, optional issuer/JWKS overrides, `SUPABASE_JWT_SECRET` (HS256 only) |
| Derived | `resolved_jwt_issuer()` → `{SUPABASE_URL}/auth/v1`; `resolved_jwks_url()` → `…/auth/v1/.well-known/jwks.json` |
| Kill switch | `PRIVATE_DATA_READS_ENABLED` (default **false**) |

### Next.js

| Mechanism | Detail |
|-----------|--------|
| Public client | `apps/web/src/lib/supabase/client.ts` reads `NEXT_PUBLIC_SUPABASE_URL` + `NEXT_PUBLIC_SUPABASE_ANON_KEY` |
| Local file | `apps/web/.env.local` (gitignored explicitly) |
| Proxy | `API_INTERNAL_BASE_URL`, `OPERATOR_LOCAL_BROWSER_PROXY_ENABLED` |
| Token helper | `apps/web/src/lib/auth/browser-access-token.ts` |

Same project URL must be used on API and web: `https://wmirifmgaftassgrfbyl.supabase.co`.

---

## 2. Configuration applied this phase

### Root `.env` (gitignored) — non-secret Auth/safety keys set

| Key | Value |
|-----|-------|
| `SUPABASE_URL` | `https://wmirifmgaftassgrfbyl.supabase.co` |
| `AUTH_JWT_MODE` | `jwks` |
| `SUPABASE_JWT_AUDIENCE` | `authenticated` |
| `PRIVATE_DATA_READS_ENABLED` | `false` |
| `OBSERVABILITY_LIVE_STREAM_ENABLED` | `false` |
| `AGENT_ALLOW_LIVE` | `false` |
| `AGENT_DRY_RUN` | `true` |
| `CRYPTONOVA_DB_TARGET` | `development` |
| `CRYPTONOVA_DEV_PROJECT_REF` | `wmirifmgaftassgrfbyl` |
| `CRYPTONOVA_ALLOW_DEV_MIGRATIONS` | `false` |

### `apps/web/.env.local` (gitignored)

| Key | Status |
|-----|--------|
| `NEXT_PUBLIC_SUPABASE_URL` | Set to approved development URL |
| `NEXT_PUBLIC_SUPABASE_ANON_KEY` | **Missing — operator must paste development anon/publishable key** |
| `OPERATOR_LOCAL_BROWSER_PROXY_ENABLED` | Set to **`false`** |
| `API_INTERNAL_BASE_URL` | `http://127.0.0.1:8000` |

### Tracked examples updated

- `apps/api/.env.development.example` — project URL aligned to `wmirifmgaftassgrfbyl`
- `apps/web/.env.development.example` — same; reminds never to use `service_role` in `NEXT_PUBLIC_*`

---

## 3. SessionStorage fallback hardening

`resolveAccessToken()` now:

- If Supabase public env is configured → **Auth session only** (signed-out returns `null`; no sessionStorage substitute).
- If Supabase public env is unset → interim sessionStorage remains (operator diagnostic only).

Any Bearer token that reaches FastAPI is still JWKS-verified; sessionStorage cannot forge signatures. The change prevents interim storage from acting as a soft bypass once Auth is wired.

---

## 4. Readiness

| Surface | Result |
|---------|--------|
| API Auth environment | **Ready** (non-secret keys present; JWKS mode; kill switches off) |
| Next.js Auth environment | **Pending** — anon key not set |
| Operator break-glass | **Disabled** (`OPERATOR_LOCAL_BROWSER_PROXY_ENABLED=false`) |
| Project alignment | API URL and Next URL target the same approved ref |
| Service-role as anon | Not used; operator must not paste service_role into `NEXT_PUBLIC_*` |

---

## 5. Operator action required

In `apps/web/.env.local`, set:

```env
NEXT_PUBLIC_SUPABASE_ANON_KEY=<development-anon-or-publishable-key>
```

Source: Supabase Dashboard → Project `wmirifmgaftassgrfbyl` → **Project Settings → API → anon / publishable** key.

Restart `npm run dev` after saving. Do not commit the filled file.

---

## 6. Explicit non-actions

- No Auth users created
- No private reads enabled
- No live trading enabled
- No secrets written to tracked files
- No Git commit/push
