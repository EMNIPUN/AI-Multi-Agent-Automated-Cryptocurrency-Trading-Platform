# Phase 3C Part 5 — Security Preflight Report

| Field | Value |
|-------|-------|
| Date | 2026-11-06 |
| Development project | `wmirifmgaftassgrfbyl` |
| Alembic revision | **`20261105_0003`** (live verified) |
| Database writes | **None** |
| New migrations | **None** |
| Private wallet reads | **Disabled** (`PRIVATE_DATA_READS_ENABLED` unset → default false) |
| Live trading | **Disabled** (`AGENT_ALLOW_LIVE=false`, `AGENT_DRY_RUN=true`) |
| Git commit/push | **None** |

---

## 1. Trust-boundary diagram

```
Browser
  │  Supabase Auth session (access JWT) OR interim sessionStorage token
  │  (NEXT_PUBLIC_SUPABASE_URL + anon key only — currently UNCONFIGURED in web env)
  ▼
Next.js (apps/web)
  │  AUTHENTICATES session retrieval only (browser client)
  │  AUTHORIZES proxy gate: require Bearer OR operator-local break-glass flag
  │  Forwards Authorization: Bearer <token> to FastAPI (no cookies / XFF)
  ▼
FastAPI (apps/api)
  │  AUTHENTICATES: JWKS/HS256 verify (iss/aud/exp/sig); reject anon/service_role
  │  AUTHORIZES (primary):
  │    - principal.user_id ownership filters (catalog)
  │    - require_active_binding_for_principal (wallet/telemetry)
  │    - PRIVATE_DATA_READS_ENABLED kill switch (fail-closed)
  │    - credential_ref allowlist (server-side only)
  ▼
Supabase PostgreSQL (project wmirifmgaftassgrfbyl)
  │  Connection role today: postgres (rolbypassrls=true)
  │  RLS policies: defense-in-depth for role `authenticated` only
  │  Schema `app` USAGE not granted to anon/authenticated
  ▼
Tables: agent_decisions, system_events, strategy_configs, exchange_account_bindings
```

### Who authenticates vs authorizes

| Hop | Authenticates user? | Authorizes data access? |
|-----|---------------------|-------------------------|
| Browser Supabase client | Session establish / refresh | No |
| Next.js proxy | No (forwards token) | Gate: missing token → 401 unless break-glass |
| FastAPI JWT verifier | **Yes** (signature, iss, aud, exp, role) | Role must be `authenticated` |
| FastAPI ownership / bindings | No | **Yes — primary isolation** |
| PostgreSQL RLS | Via `auth.uid()` when role=`authenticated` | **Defense in depth only** — **not enforced** for current `postgres` API connections |

### Application ownership vs RLS

| Control | Layer | Enforced today for API path? |
|---------|-------|------------------------------|
| JWT `sub` → `owner_user_id` equality in SQLAlchemy queries | Application | **Yes** (when private reads enabled) |
| Binding ownership / status / env / telemetry scope | Application | **Yes** (when private reads enabled) |
| SELECT-own RLS policies using `auth.uid()` | PostgreSQL | **Policies present**, but **bypassed** by `postgres` connection |
| Schema USAGE / table grants to `authenticated` | PostgreSQL | **Not granted** (extra fail-closed vs Data API) |

**Do not claim RLS protects the FastAPI connection.** Compensating controls are FastAPI ownership filters + private-reads kill switch + no broad GRANTs.

---

## 2. Development identity (live)

| Check | Result |
|-------|--------|
| Guard classification | `development` |
| Project ref | `wmirifmgaftassgrfbyl` |
| Host | `aws-0-ap-southeast-2.pooler.supabase.com` (session pooler) |
| Alembic | `20261105_0003` |
| Row counts | 0 / 0 / 0 / 0 |
| Tool | `scripts/inspect_rls_security_readonly.py` |

---

## 3. RLS policy inspection (catalog metadata)

| Item | Result |
|------|--------|
| RLS enabled (all 4 tables) | **Yes** |
| FORCE RLS | **No** (expected) |
| Table owner | `postgres` |
| Policies | 4 SELECT-own as designed |
| Policy roles | `{authenticated}` |
| Policy predicate | `owner_user_id = auth.uid()` (+ NOT NULL on catalog; + `status='active'` on bindings) |
| Forged client params | Policies use `auth.uid()`, not request query args |
| `auth.uid()` function | Present |
| `anon` / `authenticated` schema USAGE | **False** |
| `anon` table SELECT | **False** |
| App connection role | `postgres`, **`rolbypassrls=true`** |

**RLS policy inspection:** PASS with **FINDING**: privileged API DB role bypasses RLS.

Inspector finding code: `app_connection_bypasses_rls:current_role_is_super_or_bypassrls`

---

## 4. Supabase Auth / JWT configuration

| Item | Result |
|------|--------|
| Public JWKS (`…/wmirifmgaftassgrfbyl…/jwks.json`) | HTTP 200; 1 key; **ES256** / EC |
| Root `.env` `SUPABASE_URL` | **Not set** |
| Root `.env` `AUTH_JWT_MODE` | **Not set** (code default `jwks`) |
| Root `.env` `SUPABASE_JWT_SECRET` | Not set (good for JWKS mode) |
| `apps/web/.env.local` `NEXT_PUBLIC_SUPABASE_*` | **Not set** |
| Web break-glass | `OPERATOR_LOCAL_BROWSER_PROXY_ENABLED` is set locally (operator-only) |
| Code verifier | Rejects anon/service_role; requires exp/sub/iss/aud; ES256/RS256 for JWKS |

**Auth integration:** FINDINGS — JWKS endpoint for the approved project is reachable, but **application env does not yet wire `SUPABASE_URL` / Next public URL**, so live end-to-end JWT sessions are not configured.

---

## 5. Exchange account binding security (code + schema)

Verified:

- `owner_user_id` required; enrollment operator-attested
- Unique active `(provider, credential_ref)` and `(owner_user_id, provider, environment)`
- Unique `telemetry_scope_id`
- Status check: only `active` is readable
- Cross-user / forged / pending / env mismatch denied in application layer
- `credential_ref` allowlisted; no raw Bybit secrets in DB model
- Client cannot inject env var names into credential resolution
- RLS SELECT-own active rows for `authenticated` (defense in depth)

**Binding security (application):** PASS (offline). Real DB binding isolation still **Pending** (no rows; no Auth users).

---

## 6. Data API exposure

Cannot be verified programmatically without Dashboard access or Management API.

**Status: PENDING** — operator screenshot checklist in auth/integration report and gate summary.

Do **not** expose schema `app` for testing.

---

## 7. Offline tests executed

| Suite | Result |
|-------|--------|
| Part 5 preflight + auth + ownership + bindings + Part2/3 + dev guard | **109 passed** |
| Frontend vitest | **15 passed** |

New regression file: `tests/test_phase3c_part5_security_preflight.py`

---

## 8. Outstanding issues / approvals

1. **Real DB RLS isolation** requires synthetic rows + temporary `authenticated` grants or equivalent — **STOP for operator approval** (see RLS test plan).
2. Configure development `SUPABASE_URL` / JWT issuer (API) and `NEXT_PUBLIC_SUPABASE_*` (web) before live Auth E2E.
3. Prefer least-privilege DB role without `BYPASSRLS` for FastAPI (documented; not applied).
4. Confirm Data API exposed schemas exclude `app`.
5. Clear leftover shell `CRYPTONOVA_ALLOW_DEV_MIGRATIONS=yes` after Part 4 (migrations not run in Part 5).

---

## 9. Scoreboard (preflight)

| Item | Result |
|------|--------|
| Development identity | **Verified** |
| Alembic revision | `20261105_0003` |
| RLS policy inspection | **PASS (Findings: postgres BYPASSRLS)** |
| Real database RLS isolation | **Pending** (approval required) |
| Supabase Auth integration | **Findings** (JWKS OK; env unwired) |
| JWT security (code) | **PASS** |
| Exchange account binding | **PASS** (app) / Pending (DB RLS) |
| Data API exposure | **Pending** |
| FastAPI authorization | **PASS** (offline) |
| Next.js session isolation | **Findings** (no Supabase public env) |
| Python tests | **109** |
| Frontend tests | **15** |
| Database writes | None |
| New migrations | None |
| Private wallet reads | Disabled |
| Live trading | Disabled |
| Git commit/push | None |
